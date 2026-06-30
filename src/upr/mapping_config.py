"""External mapping configuration (YAML) — remap without code edits.

Lets an institution adjust how source data maps to the model without touching
Python:

  * extra **column aliases** for the importer / Slate / Jenzabar
    (e.g. map your registrar's "PROG_CD" header to program_code)
  * NetSuite **GL account buckets** and **operations departments**

Load order: ``UPR_MAPPING_FILE`` env var, else ``config/mapping.yaml`` if present,
else built-in defaults. See ``config/mapping.example.yaml``.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class MappingConfig:
    # canonical field -> list of additional accepted header strings
    column_aliases: dict[str, list[str]] = field(default_factory=dict)
    # NetSuite GL buckets: list of {field, exact|range, sign}; None -> built-ins
    netsuite_buckets: list[dict] | None = None
    # operations department names; None -> built-ins
    operations_departments: set[str] | None = None
    source_path: str | None = None


_DEFAULT = MappingConfig()
_CACHE: MappingConfig | None = None


def load_mapping(path: str) -> MappingConfig:
    """Parse a mapping YAML file into a MappingConfig."""
    import yaml  # lazy: only needed when a config file is used

    with open(path) as fh:
        data = yaml.safe_load(fh) or {}

    aliases = {k: list(v) for k, v in (data.get("column_aliases") or {}).items()}
    buckets = data.get("netsuite", {}).get("account_buckets")
    ops = data.get("netsuite", {}).get("operations_departments")
    return MappingConfig(
        column_aliases=aliases,
        netsuite_buckets=[dict(b) for b in buckets] if buckets else None,
        operations_departments={str(d).lower() for d in ops} if ops else None,
        source_path=path,
    )


def _resolve_path() -> str | None:
    env = os.getenv("UPR_MAPPING_FILE")
    if env:
        return env if Path(env).is_file() else None
    default = Path("config/mapping.yaml")
    return str(default) if default.is_file() else None


def get_mapping() -> MappingConfig:
    """Return the active mapping config (cached). Defaults if no file is found."""
    global _CACHE
    if _CACHE is not None:
        return _CACHE
    path = _resolve_path()
    _CACHE = load_mapping(path) if path else _DEFAULT
    return _CACHE


def set_mapping(config: MappingConfig | None) -> None:
    """Override the cached mapping (used by the dashboard and tests)."""
    global _CACHE
    _CACHE = config


def reset_mapping() -> None:
    """Clear the cache so the next ``get_mapping`` reloads from disk/env."""
    global _CACHE
    _CACHE = None
