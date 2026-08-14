"""DARWIN Labs — Edge Library + Graveyard store.

JSON-backed, git-friendly institutional memory. Enforces the gate rules:
no discovery advances unless the required independent gates have passed.
"""

from __future__ import annotations

import json
from pathlib import Path

from .schema import (Discovery, Evidence, EVIDENCE_REQUIREMENTS,
                     GATE_REQUIREMENTS, GATE_VERDICTS, STATUS_ORDER, STATUSES,
                     next_id, utcnow)

ROOT = Path(__file__).resolve().parent.parent
LIBRARY_PATH = ROOT / "library" / "edges.json"
GRAVEYARD_PATH = ROOT / "library" / "graveyard.json"


class GateError(Exception):
    pass


def _load(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return json.loads(path.read_text())


def _save(path: Path, records: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(records, indent=2, ensure_ascii=False) + "\n")


def load_library() -> list[Discovery]:
    return [Discovery.from_dict(d) for d in _load(LIBRARY_PATH)]


def load_graveyard() -> list[Discovery]:
    return [Discovery.from_dict(d) for d in _load(GRAVEYARD_PATH)]


def save_library(items: list[Discovery]) -> None:
    for d in items:
        d.validate()
    _save(LIBRARY_PATH, [d.to_dict() for d in items])


def save_graveyard(items: list[Discovery]) -> None:
    for d in items:
        d.validate()
    _save(GRAVEYARD_PATH, [d.to_dict() for d in items])


def get(discovery_id: str) -> Discovery | None:
    for d in load_library() + load_graveyard():
        if d.id == discovery_id:
            return d
    return None


def add(d: Discovery) -> Discovery:
    lib = load_library()
    if not d.id:
        d.id = next_id([x.id for x in lib] + [x.id for x in load_graveyard()])
    d.validate()
    d.history.append({"ts": utcnow(), "event": "created", "status": d.status})
    lib.append(d)
    save_library(lib)
    return d


def record_gate(discovery_id: str, gate: str, verdict: str, note: str = "") -> Discovery:
    """An independent gate records its verdict. Failing a required gate
    for the current target status should normally be followed by kill()."""
    if verdict not in GATE_VERDICTS:
        raise GateError(f"bad verdict {verdict!r}")
    lib = load_library()
    d = _find(lib, discovery_id)
    d.gates[gate] = verdict
    d.history.append({"ts": utcnow(), "event": f"gate:{gate}={verdict}", "note": note})
    if note:
        d.evidence.append(Evidence(date=utcnow()[:10], author=gate, note=note,
                                   kind="falsification"))
    save_library(lib)
    return d


def transition(discovery_id: str, new_status: str, note: str = "") -> Discovery:
    """Move a discovery along the lifecycle.

    Enforces three rules:
    1. Sequential progression — a discovery advances exactly ONE status at a
       time (CANDIDATE -> TESTING -> SUPPORTED -> ...). Skipping stages is
       impossible. KILLED is reachable from any status. Backward moves are
       refused; a regressed discovery must be KILLED and re-entered.
    2. Gates — every gate required for the target status must say "pass".
    3. Evidence artifacts — the target status's required evidence kinds must
       be present on the record. Verdicts without artifacts do not count.
    """
    if new_status not in STATUSES:
        raise GateError(f"bad status {new_status!r}")
    lib = load_library()
    d = _find(lib, discovery_id)
    old = d.status

    if old == "KILLED":
        raise GateError(f"{discovery_id} is in the graveyard; it cannot transition")

    # Rule 1: sequential progression (KILLED exempt — falsification respects no queue)
    if new_status != "KILLED":
        if new_status == old:
            raise GateError(f"{discovery_id} is already {old}")
        next_idx = STATUS_ORDER[old] + 1
        if STATUS_ORDER.get(new_status, -1) != next_idx:
            raise GateError(
                f"{discovery_id} cannot jump {old}->{new_status}: lifecycle is "
                f"sequential. Next allowed: {STATUSES[next_idx]} (or KILLED).")

    # Rule 2: gates
    required = GATE_REQUIREMENTS[new_status]
    missing = [g for g in required if d.gates.get(g) != "pass"]
    if missing:
        raise GateError(
            f"{discovery_id} cannot enter {new_status}: gates not passed: {missing}. "
            "No discovery promotes itself.")

    # Rule 3: evidence artifacts
    needed_kinds = EVIDENCE_REQUIREMENTS.get(new_status, ())
    if needed_kinds:
        present = {e.kind for e in d.evidence}
        if not present & set(needed_kinds):
            raise GateError(
                f"{discovery_id} cannot enter {new_status}: missing evidence artifact "
                f"of kind {'/'.join(needed_kinds)} (has: {sorted(present) or 'none'}). "
                "Gates must be backed by artifacts, not assertions.")

    if new_status == "PROMOTED" and not d.strategy_ref:
        raise GateError(
            f"{discovery_id} cannot be PROMOTED without strategy_ref — "
            "a promoted discovery must point at an entry in strategies/.")

    d.status = new_status
    d.history.append({"ts": utcnow(), "event": f"status:{old}->{new_status}", "note": note})

    if new_status == "KILLED":
        if not d.kill_cause:
            raise GateError("kill_cause is required — the graveyard remembers why")
        lib.remove(d)
        save_library(lib)
        grave = load_graveyard()
        grave.append(d)
        save_graveyard(grave)
    else:
        save_library(lib)
    return d


def add_evidence(discovery_id: str, author: str, note: str, kind: str = "observation") -> Discovery:
    lib = load_library()
    d = _find(lib, discovery_id)
    d.evidence.append(Evidence(date=utcnow()[:10], author=author, note=note, kind=kind))
    save_library(lib)
    return d


def link(discovery_id: str, other_id: str) -> Discovery:
    """Archaeologist: connect a discovery to a related past experiment."""
    lib = load_library()
    d = _find(lib, discovery_id)
    if other_id not in d.lineage:
        d.lineage.append(other_id)
        d.history.append({"ts": utcnow(), "event": f"linked:{other_id}"})
        save_library(lib)
    return d


def _find(lib: list[Discovery], discovery_id: str) -> Discovery:
    for d in lib:
        if d.id == discovery_id:
            return d
    raise KeyError(f"{discovery_id} not in library (check graveyard?)")
