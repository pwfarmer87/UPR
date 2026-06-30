"""Configuration loaded from environment / .env."""

from __future__ import annotations

import os
from dataclasses import dataclass, field

try:
    from dotenv import load_dotenv

    load_dotenv()
except Exception:  # python-dotenv optional at runtime
    pass


@dataclass
class NetSuiteConfig:
    account_id: str | None = None
    consumer_key: str | None = None
    consumer_secret: str | None = None
    token_id: str | None = None
    token_secret: str | None = None

    @property
    def is_configured(self) -> bool:
        return all(
            [
                self.account_id,
                self.consumer_key,
                self.consumer_secret,
                self.token_id,
                self.token_secret,
            ]
        )


@dataclass
class SlateConfig:
    base_url: str | None = None
    query_key: str | None = None

    @property
    def is_configured(self) -> bool:
        return bool(self.base_url and self.query_key)


@dataclass
class JenzabarConfig:
    base_url: str | None = None
    api_key: str | None = None
    db_dsn: str | None = None

    @property
    def is_configured(self) -> bool:
        return bool((self.base_url and self.api_key) or self.db_dsn)


def _opt_float(name: str) -> float | None:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return None
    return float(raw)


@dataclass
class Settings:
    data_source: str = "mock"  # mock | file | live
    fiscal_year: int = 2025
    allocation_driver: str = "credit_hours"  # credit_hours | headcount | direct_cost
    # Optional institution-wide operations pool override (used for file mode and
    # to let the dashboard set it interactively).
    operations_cost: float | None = None
    # File-import paths (UPR_DATA_SOURCE=file): one unified file, or per-source.
    import_file: str | None = None
    jenzabar_file: str | None = None
    netsuite_file: str | None = None
    slate_file: str | None = None
    netsuite: NetSuiteConfig = field(default_factory=NetSuiteConfig)
    slate: SlateConfig = field(default_factory=SlateConfig)
    jenzabar: JenzabarConfig = field(default_factory=JenzabarConfig)

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            data_source=os.getenv("UPR_DATA_SOURCE", "mock").lower(),
            fiscal_year=int(os.getenv("UPR_FISCAL_YEAR", "2025")),
            allocation_driver=os.getenv("UPR_ALLOCATION_DRIVER", "credit_hours"),
            operations_cost=_opt_float("UPR_OPERATIONS_COST"),
            import_file=os.getenv("UPR_IMPORT_FILE") or None,
            jenzabar_file=os.getenv("UPR_JENZABAR_FILE") or None,
            netsuite_file=os.getenv("UPR_NETSUITE_FILE") or None,
            slate_file=os.getenv("UPR_SLATE_FILE") or None,
            netsuite=NetSuiteConfig(
                account_id=os.getenv("NETSUITE_ACCOUNT_ID"),
                consumer_key=os.getenv("NETSUITE_CONSUMER_KEY"),
                consumer_secret=os.getenv("NETSUITE_CONSUMER_SECRET"),
                token_id=os.getenv("NETSUITE_TOKEN_ID"),
                token_secret=os.getenv("NETSUITE_TOKEN_SECRET"),
            ),
            slate=SlateConfig(
                base_url=os.getenv("SLATE_BASE_URL"),
                query_key=os.getenv("SLATE_QUERY_KEY"),
            ),
            jenzabar=JenzabarConfig(
                base_url=os.getenv("JENZABAR_BASE_URL"),
                api_key=os.getenv("JENZABAR_API_KEY"),
                db_dsn=os.getenv("JENZABAR_DB_DSN"),
            ),
        )
