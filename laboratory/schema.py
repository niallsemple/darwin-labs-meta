"""DARWIN Labs — discovery/hypothesis schema.

Every candidate edge in the laboratory is a Discovery record. The record is the
single source of truth for the Edge Library and the Graveyard.

Status lifecycle (one-way unless a gate fails):

    CANDIDATE    explorer flagged something strange
    TESTING      statistician is running falsification
    SUPPORTED    survived falsification in-sample (still not trusted)
    VALIDATED    passed out-of-sample / persistence checks
    SHADOW       paper-trading forward, execution-adjusted
    MICRO_LIVE   tiny real stakes, risk-officer approved
    PROMOTED     became a strategy (entry in strategies/)
    KILLED       falsified / decayed / untradeable -> graveyard

Gate rule (from the founding design): no discovery promotes itself.
Each gate (sceptic, statistician, execution, risk) must independently pass
before the next status transition is allowed. The store enforces this.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

STATUSES = [
    "CANDIDATE",
    "TESTING",
    "SUPPORTED",
    "VALIDATED",
    "SHADOW",
    "MICRO_LIVE",
    "PROMOTED",
    "KILLED",
]

# Gates required before entering each status.
GATE_REQUIREMENTS = {
    "CANDIDATE": [],
    "TESTING": [],
    "SUPPORTED": ["statistician"],                       # falsification survived
    "VALIDATED": ["statistician", "sceptic"],            # OOS + independent attack
    "SHADOW": ["statistician", "sceptic", "execution"],  # can it actually trade?
    "MICRO_LIVE": ["statistician", "sceptic", "execution", "risk"],
    "PROMOTED": ["statistician", "sceptic", "execution", "risk"],
    "KILLED": [],
}

GATES = ["sceptic", "statistician", "execution", "risk"]
GATE_VERDICTS = ["pending", "pass", "fail", "watch"]

# Sequential lifecycle: a discovery may only advance ONE step at a time.
# KILLED is reachable from any status (falsification respects no queue).
STATUS_ORDER = {s: i for i, s in enumerate(STATUSES) if s != "KILLED"}

# Evidence artifacts required BEFORE entering each status. A transition is
# refused unless the discovery carries at least one Evidence entry of one of
# the listed kinds. This is what makes gates falsifiable: verdicts must be
# backed by artifacts, not assertions.
EVIDENCE_REQUIREMENTS = {
    "CANDIDATE": (),
    "TESTING": (),
    # statistician's falsification run or a deterministic experiment artifact
    "SUPPORTED": ("falsification", "experiment"),
    # out-of-sample persistence evidence
    "VALIDATED": ("oos",),
    # execution-feasibility evidence (spread/slippage/fills)
    "SHADOW": ("execution",),
    # shadow-period forward P&L evidence
    "MICRO_LIVE": ("oos", "execution"),
    # live execution evidence + a strategy reference (checked separately)
    "PROMOTED": ("execution",),
    "KILLED": (),
}

ID_PATTERN = re.compile(r"^D-\d{4,}$")


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass
class Evidence:
    """One dated piece of evidence for or against the discovery."""
    date: str
    author: str            # explorer / statistician / sceptic / archaeologist / ...
    note: str
    kind: str = "observation"  # observation | falsification | experiment | oos | decay | execution


@dataclass
class Metrics:
    effect_size: Optional[float] = None      # e.g. bps/h or % return
    effect_unit: str = ""
    n: Optional[int] = None                  # sample size
    t_stat: Optional[float] = None
    p_value: Optional[float] = None
    oos_effect: Optional[float] = None       # out-of-sample effect
    oos_sharpe: Optional[float] = None
    execution_adjusted: Optional[float] = None  # net of fees/slippage
    max_drawdown: Optional[float] = None


@dataclass
class Discovery:
    id: str                                  # D-0001, D-0002, ...
    title: str
    lab: str                                 # hl_crypto | betfair | other
    status: str = "CANDIDATE"
    created: str = field(default_factory=utcnow)
    freeze_ts: Optional[str] = None          # OOS freeze timestamp
    hypothesis: str = ""                     # falsifiable statement
    falsifiable_prediction: str = ""
    kill_criteria: str = ""                  # what would kill it
    metrics: Metrics = field(default_factory=Metrics)
    gates: dict = field(default_factory=lambda: {g: "pending" for g in GATES})
    kill_cause: str = ""
    regime_notes: str = ""                   # where it works / doesn't
    lineage: list = field(default_factory=list)   # archaeologist links, e.g. ["D-0003"]
    strategy_ref: str = ""                   # path once promoted
    evidence: list = field(default_factory=list)  # list[Evidence]
    history: list = field(default_factory=list)   # status transition log

    def validate(self) -> None:
        if not ID_PATTERN.match(self.id):
            raise ValueError(f"bad discovery id {self.id!r} (want D-0001 style)")
        if self.status not in STATUSES:
            raise ValueError(f"bad status {self.status!r}")
        for g, v in self.gates.items():
            if g not in GATES or v not in GATE_VERDICTS:
                raise ValueError(f"bad gate {g}={v!r}")

    def to_dict(self) -> dict:
        d = asdict(self)
        return d

    @staticmethod
    def from_dict(d: dict) -> "Discovery":
        d = dict(d)
        d["metrics"] = Metrics(**d.get("metrics", {}))
        d["evidence"] = [Evidence(**e) for e in d.get("evidence", [])]
        return Discovery(**d)


def next_id(existing: list[str]) -> str:
    nums = [int(x.split("-")[1]) for x in existing if ID_PATTERN.match(x)]
    return f"D-{(max(nums) + 1) if nums else 1:04d}"
