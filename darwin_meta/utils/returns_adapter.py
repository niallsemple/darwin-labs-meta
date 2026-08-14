"""DARWIN Meta-Engine — Returns Adapter

Connects the decay engine to ACTUAL returns. Each SUPPORTED+ discovery can
declare a chain of returns providers in library/returns_sources.json; the
first provider with enough observations wins, and the choice is reported so
the daily summary says exactly where the numbers came from.

Provider types:

- forward_ledger: a frozen forward-scoring ledger CSV (one row per completed
  period). This is the gold standard — real shadow/forward P&L.
      {"type": "forward_ledger", "path": "...", "column": "net", "min_obs": 5}

- weekday_returns: monitoring proxy for day-of-week effects. Computes the
  equal-weight basket's daily close-to-close return from a directory of
  *_1d.csv price files and keeps only the given weekday within the last
  window_days. Uses only post-discovery recent data, so it measures whether
  the effect is STILL there, not whether it was.
      {"type": "weekday_returns", "data_dir": "...",
       "weekday": 1, "window_days": 90, "min_obs": 5}

Paths in the config may be relative to this repo's root or absolute.
Stdlib only — this module must run anywhere the daily runner runs.
"""

from __future__ import annotations

import csv
import json
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_CONFIG = ROOT / "library" / "returns_sources.json"

MIN_OBS_DEFAULT = 5


def _resolve(path_str: str) -> Path:
    p = Path(path_str).expanduser()
    if not p.is_absolute():
        p = (ROOT / p).resolve()
    return p


def _from_forward_ledger(cfg: dict) -> list[float]:
    path = _resolve(cfg["path"])
    if not path.exists():
        return []
    col = cfg.get("column", "net")
    out = []
    with open(path, newline="") as f:
        for row in csv.DictReader(f):
            try:
                out.append(float(row[col]))
            except (KeyError, TypeError, ValueError):
                continue
    return out


def _from_weekday_returns(cfg: dict) -> list[float]:
    data_dir = _resolve(cfg["data_dir"])
    if not data_dir.is_dir():
        return []
    weekday = int(cfg["weekday"])               # Monday=0 ... Sunday=6
    window_days = int(cfg.get("window_days", 90))
    cutoff = datetime.now(timezone.utc) - timedelta(days=window_days)

    # ticker -> {date: close}
    series: dict[str, dict] = {}
    for f in sorted(data_dir.glob("*_1d.csv")):
        closes = {}
        with open(f, newline="") as fh:
            for row in csv.DictReader(fh):
                try:
                    dt = datetime.fromisoformat(row["Date"])
                    closes[dt.date()] = float(row["Close"])
                except (KeyError, TypeError, ValueError):
                    continue
        if len(closes) >= 2:
            series[f.stem] = closes
    if not series:
        return []

    # union of dates, sorted; equal-weight daily basket return per date
    all_dates = sorted({d for s in series.values() for d in s})
    out = []
    for prev, cur in zip(all_dates, all_dates[1:]):
        if cur < cutoff.date():
            continue
        if datetime(cur.year, cur.month, cur.day).weekday() != weekday:
            continue
        rets = [(s[cur] / s[prev] - 1) for s in series.values()
                if cur in s and prev in s and s[prev]]
        if rets:
            out.append(sum(rets) / len(rets))
    return out


_PROVIDERS = {
    "forward_ledger": _from_forward_ledger,
    "weekday_returns": _from_weekday_returns,
}


def build_returns_source(config_path: Path | None = None) -> tuple[dict, dict]:
    """Build {discovery_id: [recent returns]} from the config's provider
    chains. Returns (returns_source, provenance); provenance maps each id to
    the provider type actually used (or why nothing was available)."""
    cfg_path = config_path or DEFAULT_CONFIG
    if not cfg_path.exists():
        return {}, {"_error": f"no returns config at {cfg_path}"}
    config = json.loads(cfg_path.read_text())

    source, provenance = {}, {}
    for disc_id, spec in config.items():
        if disc_id.startswith("_") or not isinstance(spec, dict):
            continue
        providers = spec.get("providers", [])
        chosen = None
        for p in providers:
            fn = _PROVIDERS.get(p.get("type"))
            if fn is None:
                continue
            try:
                rets = fn(p)
            except Exception as e:
                provenance[disc_id] = f"{p.get('type')} error: {e}"
                continue
            if len(rets) >= int(p.get("min_obs", MIN_OBS_DEFAULT)):
                source[disc_id] = rets
                chosen = f"{p['type']} (n={len(rets)})"
                break
        provenance[disc_id] = chosen or "no provider had enough observations"
    return source, provenance


if __name__ == "__main__":
    src, prov = build_returns_source()
    print(json.dumps({"provenance": prov,
                      "lengths": {k: len(v) for k, v in src.items()}}, indent=2))
