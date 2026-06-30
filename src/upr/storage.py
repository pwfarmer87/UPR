"""Snapshot persistence (SQLite, stdlib only).

Save a computed review as a named snapshot so trends come from real saved
history instead of re-running a synthetic year each time. Each snapshot stores
the institution totals plus every program's computed financials.

    store = SnapshotStore("data/upr.db")
    sid = store.save(result, label="FY2025 actuals")
    store.list_snapshots()                  # -> [SnapshotMeta, ...]
    store.trend()                           # institution totals across snapshots
    store.program_trend("net_margin")       # per-program metric across snapshots
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from upr.pipeline import ReviewResult

_SCHEMA = """
CREATE TABLE IF NOT EXISTS snapshots (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    label            TEXT NOT NULL,
    fiscal_year      INTEGER NOT NULL,
    data_source      TEXT,
    allocation_driver TEXT,
    created_at       TEXT NOT NULL,
    totals_json      TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS snapshot_programs (
    snapshot_id  INTEGER NOT NULL,
    program_code TEXT NOT NULL,
    program_name TEXT,
    net_margin   REAL,
    total_revenue REAL,
    enrolled_majors INTEGER,
    data_json    TEXT NOT NULL,
    FOREIGN KEY (snapshot_id) REFERENCES snapshots(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_snap_programs ON snapshot_programs(snapshot_id);
"""


@dataclass
class SnapshotMeta:
    id: int
    label: str
    fiscal_year: int
    data_source: str
    allocation_driver: str
    created_at: str
    totals: dict


class SnapshotStore:
    def __init__(self, db_path: str = "data/upr.db"):
        self.db_path = db_path
        if db_path != ":memory:":
            Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(db_path)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> SnapshotStore:
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def save(
        self, result: ReviewResult, label: str, created_at: str | None = None
    ) -> int:
        """Persist a review; returns the new snapshot id."""
        ts = created_at or datetime.now(timezone.utc).isoformat(timespec="seconds")
        cur = self._conn.execute(
            "INSERT INTO snapshots "
            "(label, fiscal_year, data_source, allocation_driver, created_at, totals_json) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                label, result.fiscal_year, ", ".join(result.sources_used),
                result.allocation_driver, ts, json.dumps(result.totals()),
            ),
        )
        snapshot_id = int(cur.lastrowid)
        rows = [
            (
                snapshot_id, f.program_code, f.program_name, f.net_margin,
                f.total_revenue, f.enrolled_majors, json.dumps(f.as_row()),
            )
            for f in result.financials
        ]
        self._conn.executemany(
            "INSERT INTO snapshot_programs "
            "(snapshot_id, program_code, program_name, net_margin, total_revenue, "
            "enrolled_majors, data_json) VALUES (?, ?, ?, ?, ?, ?, ?)",
            rows,
        )
        self._conn.commit()
        return snapshot_id

    def list_snapshots(self) -> list[SnapshotMeta]:
        rows = self._conn.execute(
            "SELECT * FROM snapshots ORDER BY fiscal_year, created_at"
        ).fetchall()
        return [
            SnapshotMeta(
                id=r["id"], label=r["label"], fiscal_year=r["fiscal_year"],
                data_source=r["data_source"], allocation_driver=r["allocation_driver"],
                created_at=r["created_at"], totals=json.loads(r["totals_json"]),
            )
            for r in rows
        ]

    def load_programs(self, snapshot_id: int) -> pd.DataFrame:
        rows = self._conn.execute(
            "SELECT data_json FROM snapshot_programs WHERE snapshot_id = ?",
            (snapshot_id,),
        ).fetchall()
        return pd.DataFrame([json.loads(r["data_json"]) for r in rows])

    def delete(self, snapshot_id: int) -> None:
        self._conn.execute("DELETE FROM snapshot_programs WHERE snapshot_id = ?",
                           (snapshot_id,))
        self._conn.execute("DELETE FROM snapshots WHERE id = ?", (snapshot_id,))
        self._conn.commit()

    def trend(self) -> pd.DataFrame:
        """Institution totals across saved snapshots (one row per snapshot)."""
        metas = self.list_snapshots()
        if not metas:
            return pd.DataFrame()
        return pd.DataFrame([
            {
                "id": m.id, "label": m.label, "fiscal_year": m.fiscal_year,
                "created_at": m.created_at,
                "total_revenue": m.totals.get("total_revenue"),
                "total_cost": m.totals.get("total_cost"),
                "net_margin": m.totals.get("net_margin"),
                "net_margin_ratio": m.totals.get("net_margin_ratio"),
                "enrolled_majors": m.totals.get("enrolled_majors"),
            }
            for m in metas
        ])

    def program_trend(self, metric: str = "net_margin") -> pd.DataFrame:
        """A per-program metric across snapshots (programs × fiscal years)."""
        metas = {m.id: m for m in self.list_snapshots()}
        if not metas:
            return pd.DataFrame()
        frames = []
        for sid, meta in metas.items():
            df = self.load_programs(sid)
            if df.empty or metric not in df.columns:
                continue
            sub = df[["program_code", "program_name", metric]].copy()
            sub["fiscal_year"] = meta.fiscal_year
            frames.append(sub)
        if not frames:
            return pd.DataFrame()
        long = pd.concat(frames, ignore_index=True)
        wide = long.pivot_table(
            index=["program_code", "program_name"], columns="fiscal_year",
            values=metric, aggfunc="first",
        ).reset_index()
        wide.columns.name = None
        return wide
