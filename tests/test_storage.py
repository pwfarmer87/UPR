from upr.config import Settings
from upr.pipeline import run_review
from upr.storage import SnapshotStore


def _result(year):
    return run_review(Settings(data_source="mock", fiscal_year=year))


def test_save_and_list_roundtrip():
    with SnapshotStore(":memory:") as store:
        sid = store.save(_result(2025), label="FY2025")
        assert isinstance(sid, int)
        metas = store.list_snapshots()
        assert len(metas) == 1
        assert metas[0].label == "FY2025"
        assert metas[0].fiscal_year == 2025
        assert metas[0].totals["total_revenue"] > 0


def test_load_programs_returns_full_financials():
    with SnapshotStore(":memory:") as store:
        sid = store.save(_result(2025), label="FY2025")
        df = store.load_programs(sid)
        assert {"program_code", "net_margin", "total_cost"} <= set(df.columns)
        assert len(df) == len(_result(2025).financials)


def test_trend_across_snapshots():
    with SnapshotStore(":memory:") as store:
        store.save(_result(2024), label="FY2024")
        store.save(_result(2025), label="FY2025")
        store.save(_result(2026), label="FY2026")
        trend = store.trend()
        assert len(trend) == 3
        revs = trend.sort_values("fiscal_year")["total_revenue"].tolist()
        assert revs == sorted(revs)  # sample data grows
        wide = store.program_trend("net_margin")
        assert 2024 in wide.columns and 2026 in wide.columns


def test_delete_removes_snapshot_and_programs():
    with SnapshotStore(":memory:") as store:
        sid = store.save(_result(2025), label="FY2025")
        store.delete(sid)
        assert store.list_snapshots() == []
        assert store.load_programs(sid).empty
