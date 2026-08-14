"""DARWIN Discovery — Data Adapters

One adapter per laboratory. Each returns a uniform structure:

    {
      "freq": "1d" | "1h",
      "series": { name: [(datetime, close), ...] },   # sorted ascending
    }

Stdlib only. Paths are resolved against the meta repo root, so sibling
laboratories (darwin-labs, ft/hl_monitor) are referenced relatively.
New labs register here; the scanners don't care where data came from.
"""

from __future__ import annotations

import csv
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent

EQUITIES_DAILY_DIR = ROOT.parent / "darwin-labs" / "labs" / "equities" / "data_repl"
GOLD_DATA_DIR = ROOT.parent / "darwin-labs" / "labs" / "gold" / "data"
CRYPTO_1H_DIR = ROOT.parent / "ft" / "hl_monitor" / "data"


def _parse_dt(s: str) -> datetime | None:
    s = s.strip()
    try:
        return datetime.fromisoformat(s)
    except ValueError:
        pass
    try:  # epoch milliseconds
        return datetime.fromtimestamp(int(s) / 1000, tz=timezone.utc)
    except (ValueError, OSError):
        return None


def _load_csv_series(path: Path, date_col: str, close_col: str) -> list:
    out = []
    with open(path, newline="") as f:
        for row in csv.DictReader(f):
            dt = _parse_dt(row.get(date_col, ""))
            try:
                close = float(row.get(close_col, ""))
            except (TypeError, ValueError):
                continue
            if dt is not None:
                out.append((dt, close))
    out.sort(key=lambda x: x[0])
    return out


def load_equities_daily() -> dict:
    """13-ETF daily closes from the equities lab replication data."""
    series = {}
    if not EQUITIES_DAILY_DIR.is_dir():
        return {"freq": "1d", "series": {}}
    for f in sorted(EQUITIES_DAILY_DIR.glob("*_1d.csv")):
        name = f.stem.replace("_1d", "").upper()
        s = _load_csv_series(f, "Date", "Close")
        if len(s) >= 60:
            series[name] = s
    return {"freq": "1d", "series": series}


def load_gold_daily() -> dict:
    path = GOLD_DATA_DIR / "gc_1d.csv"
    series = {}
    if path.exists():
        # gold CSVs use ts/close (lowercase), unlike the equities Date/Close
        s = _load_csv_series(path, "ts", "close")
        if len(s) >= 60:
            series["GC"] = s
    return {"freq": "1d", "series": series}


def load_crypto_1h() -> dict:
    """Hourly crypto perps from the hl_monitor data cache."""
    series = {}
    if not CRYPTO_1H_DIR.is_dir():
        return {"freq": "1h", "series": {}}
    for f in sorted(CRYPTO_1H_DIR.glob("*_1h.csv")):
        name = f.stem.replace("_1h", "").upper()
        s = _load_csv_series(f, "datetime", "close")
        if len(s) >= 24 * 30:  # at least a month of hours
            series[name] = s
    return {"freq": "1h", "series": series}


ADAPTERS = {
    "equities_daily": load_equities_daily,
    "gold_daily": load_gold_daily,
    "crypto_1h": load_crypto_1h,
}


def available_adapters() -> dict[str, str]:
    """Name -> short status string, for reporting."""
    out = {}
    for name, fn in ADAPTERS.items():
        try:
            d = fn()
            n = len(d["series"])
            out[name] = f"{n} series" if n else "no data"
        except Exception as e:
            out[name] = f"error: {e}"
    return out
