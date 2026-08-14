"""DARWIN Labs — Experiment Engine.

The research-truth layer. Every hypothesis gets an ExperimentSpec that freezes
exactly what will be tested, on what data, with what costs, before anyone looks
at a result. Running the experiment produces an immutable ExperimentResult.

Design rules:
- A spec is hashed (sha256 of its canonical JSON). The hash is the spec's
  identity; change anything and it is a NEW spec.
- Results are write-once files keyed by their own hash. record_result()
  refuses to overwrite. No LLM, agent, or daily job can edit history.
- A result must reference a spec_hash that already exists on disk. You cannot
  record results for an experiment that was never specified.
- LLMs may propose specs and critique results. They never write results by
  hand — results come from deterministic experiment runners.

Storage layout (git-friendly, append-only):
    library/experiments/specs/<spec_hash>.json
    library/experiments/results/<result_hash>.json
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional

from .schema import utcnow

ROOT = Path(__file__).resolve().parent.parent
SPEC_DIR = ROOT / "library" / "experiments" / "specs"
RESULT_DIR = ROOT / "library" / "experiments" / "results"


class ExperimentError(Exception):
    pass


def _canonical(d: dict) -> str:
    """Deterministic JSON: sorted keys, no whitespace, floats normalised."""
    return json.dumps(d, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _hash(d: dict) -> str:
    return hashlib.sha256(_canonical(d).encode("utf-8")).hexdigest()[:16]


@dataclass
class ExperimentSpec:
    """The frozen definition of one experiment. Hash = identity."""
    discovery_id: str                    # D-0001 this experiment tests
    dataset: str                         # e.g. "hl_crypto_1h", "betfair_inplay"
    dataset_hash: str                    # hash of the exact data snapshot
    universe: list[str]                  # instruments included
    discovery_window: tuple[str, str]    # (start, end) ISO dates — in-sample
    oos_window: tuple[str, str]          # frozen out-of-sample window, untouched until validation
    features: dict                       # exact feature definitions
    fees_bps: float = 0.0
    slippage_bps: float = 0.0
    spread_model: str = "none"           # none | fixed | proportional
    seed: int = 0
    hypothesis_version: int = 1
    kill_criteria: str = ""
    created: str = field(default_factory=utcnow)

    def canonical_dict(self) -> dict:
        d = asdict(self)
        d["discovery_window"] = list(self.discovery_window)
        d["oos_window"] = list(self.oos_window)
        return d

    def spec_hash(self) -> str:
        # 'created' is excluded: hashing the WHAT, not the WHEN
        d = self.canonical_dict()
        d.pop("created", None)
        return _hash(d)

    def validate(self) -> None:
        if not self.discovery_id:
            raise ExperimentError("spec needs a discovery_id")
        if not self.dataset or not self.dataset_hash:
            raise ExperimentError("spec needs dataset AND dataset_hash — "
                                  "no experiment runs on unspecified data")
        if not self.universe:
            raise ExperimentError("spec universe is empty")
        ds, de = self.discovery_window
        os_, oe = self.oos_window
        if not (ds < de and os_ < oe):
            raise ExperimentError("windows must be (start, end) with start < end")
        if de > os_:
            raise ExperimentError(
                f"discovery window ends {de} AFTER oos window starts {os_} — "
                "the OOS vault must stay untouched by discovery")


@dataclass
class ExperimentResult:
    """Immutable output of running one spec. Written once, never edited."""
    spec_hash: str
    discovery_id: str
    metrics: dict                        # effect, n, t, p, ci, oos_effect, sharpe, trials_tested, ...
    runner: str = ""                     # which deterministic runner produced this
    created: str = field(default_factory=utcnow)
    result_hash: str = ""

    def compute_hash(self) -> str:
        d = {"spec_hash": self.spec_hash, "discovery_id": self.discovery_id,
             "metrics": self.metrics, "runner": self.runner}
        return _hash(d)


def save_spec(spec: ExperimentSpec) -> str:
    """Persist a spec. Idempotent: re-saving an identical spec is a no-op.
    A DIFFERENT spec body under an existing hash is impossible by construction
    (hash covers the body), so a collision means corruption — refuse."""
    spec.validate()
    h = spec.spec_hash()
    path = SPEC_DIR / f"{h}.json"
    if path.exists():
        existing = json.loads(path.read_text())
        if _hash({k: v for k, v in existing.items() if k != "created"}) != h:
            raise ExperimentError(f"spec hash collision/corruption at {path}")
        return h
    path.parent.mkdir(parents=True, exist_ok=True)
    body = spec.canonical_dict()
    body["spec_hash"] = h
    path.write_text(json.dumps(body, indent=2, ensure_ascii=False) + "\n")
    return h


def load_spec(spec_hash: str) -> dict:
    path = SPEC_DIR / f"{spec_hash}.json"
    if not path.exists():
        raise ExperimentError(f"no spec with hash {spec_hash}")
    return json.loads(path.read_text())


def record_result(result: ExperimentResult) -> str:
    """Write a result ONCE. The file name is the result hash; an existing
    file is never modified. If the same spec is re-run, the new run gets a
    new file (metrics/runner may differ) — history accretes, never mutates."""
    # Gate: results only for specs that exist. No spec, no truth-claim.
    load_spec(result.spec_hash)
    h = result.compute_hash()
    result.result_hash = h
    path = RESULT_DIR / f"{h}.json"
    if path.exists():
        raise ExperimentError(
            f"result {h} already exists — results are immutable. "
            "A re-run with different output is a NEW result, not an edit.")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(asdict(result), indent=2, ensure_ascii=False) + "\n")
    return h


def results_for_spec(spec_hash: str) -> list[dict]:
    if not RESULT_DIR.exists():
        return []
    out = []
    for p in sorted(RESULT_DIR.glob("*.json")):
        d = json.loads(p.read_text())
        if d.get("spec_hash") == spec_hash:
            out.append(d)
    return out


def results_for_discovery(discovery_id: str) -> list[dict]:
    """Every experiment result ever recorded for a discovery, newest last."""
    if not RESULT_DIR.exists():
        return []
    out = []
    for p in sorted(RESULT_DIR.glob("*.json")):
        d = json.loads(p.read_text())
        if d.get("discovery_id") == discovery_id:
            out.append(d)
    return sorted(out, key=lambda d: d.get("created", ""))


def latest_metrics(discovery_id: str) -> Optional[dict]:
    """The most recent verified metrics for a discovery, or None.
    This is what agents should be HANDED — they critique, they never calculate."""
    rs = results_for_discovery(discovery_id)
    if not rs:
        return None
    latest = rs[-1]
    return {
        "result_hash": latest["result_hash"],
        "spec_hash": latest["spec_hash"],
        "created": latest.get("created"),
        "metrics": latest.get("metrics", {}),
    }
