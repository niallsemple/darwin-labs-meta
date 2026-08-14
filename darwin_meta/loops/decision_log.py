"""DARWIN Meta-Engine — Decision Log

Append-only structured record of every agent decision tied to a discovery.
This is the raw material for outcome attribution: without it, agent verdicts
exist only inside markdown reports and can never be scored against reality.

One JSON per line:
    {"ts": ..., "agent": "statistician", "discovery_id": "D-0004",
     "decision": "pass", "detail": {...}}

Agents decide here; outcome_attribution.py judges them later.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

DECISIONS_PATH = Path(__file__).resolve().parent / "decisions.jsonl"


def log_decision(agent: str, discovery_id: str, decision: str,
                 detail: dict | None = None, path: Path = DECISIONS_PATH) -> None:
    rec = {
        "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "agent": agent,
        "discovery_id": discovery_id,
        "decision": decision,
        "detail": detail or {},
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def load_decisions(path: Path = DECISIONS_PATH) -> list[dict]:
    if not path.exists():
        return []
    out = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if line:
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return out
