"""DARWIN Self-Improve — Edge Tracker

Tracks whether code improvements actually lead to new discoveries.
Takes a snapshot of the library before an improvement, then compares
after a cooldown period to see if edge production increased.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parent.parent.parent
SNAPSHOT_DIR = ROOT / ".edge_snapshots"
SNAPSHOT_DIR.mkdir(exist_ok=True)


@dataclass
class LibrarySnapshot:
    timestamp: str
    total_discoveries: int
    supported_count: int
    validated_count: int
    graveyard_count: int
    avg_effect_size: float | None
    top_labs: list[str]


def take_snapshot(label: str = "") -> LibrarySnapshot:
    """Snapshot the current library state."""
    lib_path = ROOT / "library" / "edges.json"
    grave_path = ROOT / "library" / "graveyard.json"

    lib = json.loads(lib_path.read_text()) if lib_path.exists() else []
    grave = json.loads(grave_path.read_text()) if grave_path.exists() else []

    effects = [d.get("metrics", {}).get("effect_size", 0) for d in lib if d.get("metrics", {}).get("effect_size") is not None]
    avg_effect = sum(effects) / len(effects) if effects else None

    snap = LibrarySnapshot(
        timestamp=datetime.now(timezone.utc).isoformat(),
        total_discoveries=len(lib),
        supported_count=sum(1 for d in lib if d["status"] == "SUPPORTED"),
        validated_count=sum(1 for d in lib if d["status"] == "VALIDATED"),
        graveyard_count=len(grave),
        avg_effect_size=round(avg_effect, 4) if avg_effect is not None else None,
        top_labs=[d["lab"] for d in lib[:5]],
    )

    fname = f"snapshot_{label}_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.json"
    (SNAPSHOT_DIR / fname).write_text(json.dumps(snap.__dict__, ensure_ascii=False) + "\n")
    return snap


def compare_snapshots(before: LibrarySnapshot, after: LibrarySnapshot) -> dict:
    """Compare two snapshots and report whether edges improved."""
    return {
        "delta_total": after.total_discoveries - before.total_discoveries,
        "delta_supported": after.supported_count - before.supported_count,
        "delta_validated": after.validated_count - before.validated_count,
        "delta_graveyard": after.graveyard_count - before.graveyard_count,
        "delta_avg_effect": (after.avg_effect_size or 0) - (before.avg_effect_size or 0),
        "improved": after.supported_count + after.validated_count > before.supported_count + before.validated_count,
        "before_time": before.timestamp,
        "after_time": after.timestamp,
    }


def load_latest_snapshot(label: str = "") -> Optional[LibrarySnapshot]:
    """Load the most recent snapshot matching label."""
    files = sorted(SNAPSHOT_DIR.glob(f"snapshot_{label}*.json"), reverse=True)
    if not files:
        return None
    data = json.loads(files[0].read_text())
    return LibrarySnapshot(**data)


if __name__ == "__main__":
    snap = take_snapshot("manual")
    print(json.dumps(snap.__dict__, indent=2))
