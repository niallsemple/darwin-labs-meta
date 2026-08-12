"""DARWIN Meta-Engine — Decay Detection

A SUPPORTED discovery is not safe. It can decay:
- Effect size shrinks over time (regime change)
- P-values drift upward (the edge was a fluke)
- New data falsifies the kill criteria

This module periodically re-evaluates SUPPORTED+ discoveries
and flags those showing decay signals. It does NOT kill them —
that decision requires the full board meeting.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from laboratory.stats import one_sample_t, sharpe, max_drawdown


@dataclass
class DecayReport:
    discovery_id: str
    title: str
    decay_score: float  # 0 = healthy, 1 = full decay
    signals: list[str]  # human-readable decay signals
    recommendation: str  # watch / investigate / escalate


def _days_since(dt_str: str) -> int:
    """Approximate days since an ISO datetime string."""
    try:
        then = datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
        now = datetime.now(timezone.utc)
        return max(0, int((now - then).total_seconds() / 86400))
    except Exception:
        return 0


def detect_decay(discovery: dict, recent_returns: list[float] | None = None) -> DecayReport:
    """Evaluate a single discovery for decay signals.

    Args:
        discovery: A discovery dict from the library.
        recent_returns: Optional list of recent daily returns for this discovery.
    """
    signals = []
    score = 0.0
    d = discovery
    metrics = d.get("metrics", {})

    # Signal 1: Stale — no new evidence in 14+ days
    last_evidence = d.get("evidence", [])
    if last_evidence:
        last_date = last_evidence[-1].get("date", d.get("created", ""))
        days_stale = _days_since(last_date) if isinstance(last_date, str) else 999
        if days_stale > 14:
            signals.append(f"No new evidence in {days_stale} days")
            score += min(0.3, days_stale / 100)

    # Signal 2: Effect size dropped
    orig_effect = metrics.get("effect_size")
    if orig_effect is not None and recent_returns:
        current = one_sample_t(recent_returns)
        if current.get("p") is not None and current["p"] > 0.10:
            signals.append(f"Recent p-value {current['p']:.3f} > 0.10 (was significant)")
            score += 0.25
        if current.get("mean") is not None:
            if orig_effect != 0 and abs(current["mean"]) < abs(orig_effect) * 0.5:
                signals.append(f"Effect size shrank: {current['mean']:.4f} vs original {orig_effect:.4f}")
                score += 0.25

    # Signal 3: Negative Sharpe on recent window
    if recent_returns and len(recent_returns) >= 5:
        recent_sharpe = sharpe(recent_returns, periods_per_year=252)
        if recent_sharpe is not None and recent_sharpe < 0:
            signals.append(f"Negative recent Sharpe: {recent_sharpe}")
            score += 0.20

    # Signal 4: Max drawdown exceeded threshold
    if recent_returns and len(recent_returns) >= 2:
        equity = [1.0]
        for r in recent_returns:
            equity.append(equity[-1] * (1 + r))
        mdd = max_drawdown(equity)
        if mdd is not None and mdd < -0.10:
            signals.append(f"Max drawdown {mdd:.1%} exceeded -10% threshold")
            score += 0.20

    # Signal 5: Too long in SUPPORTED without advancing
    if d.get("status") == "SUPPORTED":
        days_supported = _days_since(d.get("created", ""))
        if days_supported > 30:
            signals.append(f"Stuck in SUPPORTED for {days_supported} days without advancing")
            score += min(0.2, days_supported / 300)

    score = min(1.0, score)

    if score >= 0.7:
        rec = "escalate"
    elif score >= 0.4:
        rec = "investigate"
    elif score >= 0.2:
        rec = "watch"
    else:
        rec = "healthy"

    return DecayReport(
        discovery_id=d["id"],
        title=d["title"],
        decay_score=round(score, 3),
        signals=signals,
        recommendation=rec,
    )


def scan_library(library_path: Path, returns_source: dict[str, list[float]] | None = None) -> list[DecayReport]:
    """Scan all SUPPORTED/VALIDATED discoveries for decay.

    Args:
        library_path: Path to edges.json
        returns_source: Optional mapping of discovery_id -> recent daily returns
    """
    lib = json.loads(library_path.read_text()) if library_path.exists() else []
    reports = []
    for d in lib:
        if d["status"] in ("SUPPORTED", "VALIDATED", "SHADOW"):
            ret = returns_source.get(d["id"]) if returns_source else None
            report = detect_decay(d, ret)
            if report.signals:
                reports.append(report)
    return reports


def render_decay_report(reports: list[DecayReport]) -> str:
    """Render decay reports as markdown."""
    if not reports:
        return "# Decay Report\n\nNo decay signals detected. All SUPPORTED+ discoveries look healthy.\n"

    lines = ["# Decay Report", f"\n{len(reports)} discoveries showing decay signals:\n"]
    for r in sorted(reports, key=lambda x: x.decay_score, reverse=True):
        emoji = {"healthy": "🟢", "watch": "🟡", "investigate": "🟠", "escalate": "🔴"}.get(r.recommendation, "⚪")
        lines.append(f"## {emoji} {r.discovery_id} — {r.title}")
        lines.append(f"**Decay score:** {r.decay_score:.2f} | **Action:** {r.recommendation.upper()}")
        lines.append("\nSignals:")
        for sig in r.signals:
            lines.append(f"- {sig}")
        lines.append("")
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    import sys
    lib_path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("library/edges.json")
    reports = scan_library(lib_path)
    print(render_decay_report(reports))
