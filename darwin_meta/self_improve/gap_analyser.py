"""DARWIN Self-Improve — Gap Analyser

Uses the local LLM to compare DARWIN's current capabilities against
a GitHub repo fingerprint and decide whether the repo has something
worth adding.

CRITICAL: this ONLY uses the local llama-server. No API calls.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from darwin_meta.utils.llm_bridge import LLMBridge


@dataclass
class GapReport:
    repo_name: str
    useful: bool                      # LLM says yes/no
    confidence: float                 # 0.0–1.0
    gaps: list[str]                   # what DARWIN is missing
    implementation_plan: str          # high-level plan
    risk_assessment: str              # could this break anything?
    priority: str                     # high / medium / low


# Snapshot of DARWIN's current capabilities (kept small for CPU context)
DARWIN_CAPABILITIES = """
DARWIN Labs Current Capabilities (v2026-08-12):
1. Discovery lifecycle: CANDIDATE→TESTING→SUPPORTED→VALIDATED→SHADOW→MICRO_LIVE→PROMOTED/KILLED
2. Gate system: statistician, sceptic, execution, risk must independently pass
3. Agents: Explorer, Statistician, Sceptic, CEO, Archaeologist (new)
4. Meta-learning: tracks agent performance, rotates prompts when underperforming
5. Decay detection: auto-flags stale discoveries by sample size, Sharpe, drawdown
6. Dashboard: HTML report with library state, graveyard, agent performance
7. Stats: t-tests, Welch, sign consistency, BH-FDR, walk-forward splits, Sharpe, max drawdown
8. Library store: JSON-backed with git-friendly history
9. AI Board Meeting: daily agent-driven strategic review
10. Steering committee: daily K3 check for course correction
"""


def analyse_gap(repo_fp, llm: Optional[LLMBridge] = None) -> GapReport:
    """Ask the local LLM whether a repo has useful gaps for DARWIN."""
    llm = llm or LLMBridge()

    # Build compact repo description
    flags = []
    if repo_fp.has_backtester: flags.append("backtester")
    if repo_fp.has_risk_mgmt: flags.append("risk_mgmt")
    if repo_fp.has_data_pipeline: flags.append("data_pipeline")
    if repo_fp.has_ml: flags.append("ml")
    if repo_fp.has_options: flags.append("options")
    if repo_fp.has_crypto: flags.append("crypto")

    repo_desc = (
        f"Repo: {repo_fp.full_name}\n"
        f"Stars: {repo_fp.stars}\n"
        f"Language: {repo_fp.language}\n"
        f"Topics: {', '.join(repo_fp.topics[:5])}\n"
        f"Flags: {', '.join(flags)}\n"
        f"Description: {repo_fp.description[:300]}\n"
        f"README excerpt:\n{repo_fp.readme_summary[:1500]}\n"
        f"File tree (sample):\n" + "\n".join(repo_fp.file_tree[:30]) + "\n"
    )

    messages = [
        {"role": "system", "content": (
            "You are the DARWIN Self-Improvement Evaluator. Your job is to compare "
            "a GitHub repo against DARWIN's current capabilities and decide whether "
            "adopting anything from it would help DARWIN find new trading edges. "
            "Be ruthless: most repos are redundant. Only recommend adoption if the "
            "repo clearly has something DARWIN lacks AND that thing is directly "
            "useful for alpha generation."
        )},
        {"role": "user", "content": (
            f"{DARWIN_CAPABILITIES}\n\n"
            f"--- NEW REPO TO EVALUATE ---\n\n"
            f"{repo_desc}\n\n"
            "Return ONLY valid JSON matching this schema:\n"
            '{\n'
            '  "useful": true or false,\n'
            '  "confidence": 0.0 to 1.0,\n'
            '  "gaps": ["list of specific capabilities DARWIN is missing"],\n'
            '  "implementation_plan": "1-paragraph plan for how to add this",\n'
            '  "risk_assessment": "what could go wrong",\n'
            '  "priority": "high" | "medium" | "low"\n'
            '}\n'
            "No markdown, no commentary outside the JSON."
        )},
    ]

    schema = {
        "type": "object",
        "properties": {
            "useful": {"type": "boolean"},
            "confidence": {"type": "number"},
            "gaps": {"type": "array", "items": {"type": "string"}},
            "implementation_plan": {"type": "string"},
            "risk_assessment": {"type": "string"},
            "priority": {"type": "string", "enum": ["high", "medium", "low"]},
        },
        "required": ["useful", "confidence", "gaps", "implementation_plan", "risk_assessment", "priority"],
    }

    try:
        result = llm.structured(messages, schema, temperature=0.2, max_tokens=1024)
        return GapReport(
            repo_name=repo_fp.full_name,
            useful=result.get("useful", False),
            confidence=result.get("confidence", 0.0),
            gaps=result.get("gaps", []),
            implementation_plan=result.get("implementation_plan", ""),
            risk_assessment=result.get("risk_assessment", ""),
            priority=result.get("priority", "low"),
        )
    except Exception as e:
        print(f"[Gap Analyser] LLM evaluation failed for {repo_fp.full_name}: {e}")
        return GapReport(
            repo_name=repo_fp.full_name,
            useful=False,
            confidence=0.0,
            gaps=[],
            implementation_plan="",
            risk_assessment=f"Evaluation failed: {e}",
            priority="low",
        )


if __name__ == "__main__":
    import sys
    from darwin_meta.self_improve.github_scout import load_cache
    cache = load_cache()
    if not cache:
        print("No cached repos. Run github_scout.py first.")
        sys.exit(1)
    repo = list(cache.values())[0]
    report = analyse_gap(repo)
    print(json.dumps(report.__dict__, indent=2))
