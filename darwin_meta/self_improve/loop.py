"""DARWIN Self-Improve — Main Loop Orchestrator

The self-improvement engine. One run:
1. Scout GitHub for repos
2. Evaluate each against DARWIN's capabilities (local LLM only)
3. If approved with high confidence, implement
4. Take before/after snapshots to track edge production
5. Log everything

Usage:
    python3 scripts/self_improve.py
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from darwin_meta.utils.llm_bridge import LLMBridge
from darwin_meta.self_improve.github_scout import scout, load_cache
from darwin_meta.self_improve.gap_analyser import analyse_gap
from darwin_meta.self_improve.implementer import implement
from darwin_meta.self_improve.edge_tracker import take_snapshot, compare_snapshots, load_latest_snapshot

ROOT = Path(__file__).resolve().parent.parent.parent
REPORT_PATH = ROOT / "reports" / f"self-improve-{datetime.now(timezone.utc).strftime('%Y-%m-%d')}.md"


def run_one_cycle(llm: Optional[LLMBridge] = None,
                  max_repos: int = 3,
                  min_confidence: float = 0.7,
                  max_implementations: int = 1) -> dict:
    """Run one self-improvement cycle.

    Args:
        max_repos: how many repos to evaluate this cycle
        min_confidence: only implement if LLM confidence >= this
        max_implementations: max new features to add per cycle
    """
    llm = llm or LLMBridge()
    summary = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "repos_scouted": 0,
        "repos_evaluated": 0,
        "approved": [],
        "implemented": [],
        "rejected": [],
        "errors": [],
    }

    print("=" * 60)
    print("  DARWIN Self-Improvement Cycle")
    print("=" * 60)

    # 1. Before snapshot
    print("\n[1/5] Taking before snapshot...")
    before_snap = take_snapshot("before")
    print(f"  → {before_snap.total_discoveries} discoveries, "
          f"{before_snap.supported_count} supported, {before_snap.validated_count} validated")

    # 2. Scout GitHub
    print(f"\n[2/5] Scouting GitHub (max {max_repos} repos)...")
    repos = scout(max_repos=max_repos, max_new_clones=2)
    summary["repos_scouted"] = len(repos)
    print(f"  → {len(repos)} repos to evaluate")

    # 3. Evaluate each repo
    print(f"\n[3/5] Evaluating gaps with local LLM...")
    implemented_count = 0
    for repo_fp in repos:
        print(f"\n  Evaluating: {repo_fp.full_name} ({repo_fp.stars}★)")
        try:
            report = analyse_gap(repo_fp, llm)
            summary["repos_evaluated"] += 1
            print(f"    useful={report.useful} confidence={report.confidence:.2f} priority={report.priority}")

            if report.useful and report.confidence >= min_confidence:
                summary["approved"].append({
                    "repo": report.repo_name,
                    "confidence": report.confidence,
                    "priority": report.priority,
                    "gaps": report.gaps,
                })

                if implemented_count < max_implementations:
                    print(f"    → IMPLEMENTING (gap: {report.gaps[0][:60]}...)")
                    result = implement(report, llm)
                    if result.success:
                        summary["implemented"].append({
                            "repo": report.repo_name,
                            "files_created": result.files_created,
                            "tests_added": result.tests_added,
                        })
                        implemented_count += 1
                        print(f"    → SUCCESS: {len(result.files_created)} files, {len(result.tests_added)} tests")
                    else:
                        summary["errors"].append(f"Implement failed for {report.repo_name}: {result.error}")
                        print(f"    → FAILED: {result.error}")
                else:
                    print(f"    → APPROVED but implementation limit reached")
            else:
                summary["rejected"].append({
                    "repo": report.repo_name,
                    "reason": "not useful" if not report.useful else "low confidence",
                    "confidence": report.confidence,
                })
                print(f"    → REJECTED")

            time.sleep(2)  # CPU model breathing room
        except Exception as e:
            summary["errors"].append(f"Evaluation error for {repo_fp.full_name}: {e}")
            print(f"    → ERROR: {e}")

    # 4. After snapshot (immediate — for baseline; real comparison needs days)
    print(f"\n[4/5] Taking after snapshot...")
    after_snap = take_snapshot("after")
    comparison = compare_snapshots(before_snap, after_snap)
    print(f"  → Δ discoveries: {comparison['delta_total']:+d}, "
          f"Δ supported: {comparison['delta_supported']:+d}")

    # 5. Generate report
    print(f"\n[5/5] Writing report...")
    _write_report(summary, comparison, REPORT_PATH)
    print(f"  → {REPORT_PATH}")

    print("\n" + "=" * 60)
    print("  Self-Improvement Cycle Complete")
    print("=" * 60)
    print(f"\n  Approved: {len(summary['approved'])} | Implemented: {len(summary['implemented'])} | Rejected: {len(summary['rejected'])}")
    if summary['errors']:
        print(f"  Errors: {len(summary['errors'])}")

    return summary


def _write_report(summary: dict, comparison: dict, path: Path) -> None:
    lines = [
        "# DARWIN Self-Improvement Report",
        f"_Cycle run: {summary['timestamp'][:10]}_",
        "",
        "## Summary",
        f"- Repos scouted: {summary['repos_scouted']}",
        f"- Repos evaluated: {summary['repos_evaluated']}",
        f"- Approved: {len(summary['approved'])}",
        f"- Implemented: {len(summary['implemented'])}",
        f"- Rejected: {len(summary['rejected'])}",
        f"- Errors: {len(summary['errors'])}",
        "",
        "## Edge Impact (immediate)",
        f"- Δ total discoveries: {comparison['delta_total']:+d}",
        f"- Δ supported: {comparison['delta_supported']:+d}",
        f"- Δ validated: {comparison['delta_validated']:+d}",
        f"- Δ graveyard: {comparison['delta_graveyard']:+d}",
        f"- Δ avg effect: {comparison['delta_avg_effect']:+.4f}",
        "",
    ]

    if summary["approved"]:
        lines += ["## Approved Repos", ""]
        for a in summary["approved"]:
            lines.append(f"- **{a['repo']}** (confidence {a['confidence']:.2f}, {a['priority']})")
            for g in a.get("gaps", [])[:3]:
                lines.append(f"  - {g}")
        lines.append("")

    if summary["implemented"]:
        lines += ["## Implementations", ""]
        for i in summary["implemented"]:
            lines.append(f"- **{i['repo']}**")
            for f in i.get("files_created", []):
                lines.append(f"  - Created: `{f}`")
            for t in i.get("tests_added", []):
                lines.append(f"  - Test: `{t}`")
        lines.append("")

    if summary["rejected"]:
        lines += ["## Rejected Repos", ""]
        for r in summary["rejected"]:
            lines.append(f"- {r['repo']} — {r['reason']} (confidence {r['confidence']:.2f})")
        lines.append("")

    if summary["errors"]:
        lines += ["## Errors", ""]
        for e in summary["errors"]:
            lines.append(f"- {e}")
        lines.append("")

    lines.append("---")
    lines.append("*This report was generated by the DARWIN Self-Improvement Engine.*")

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n")


if __name__ == "__main__":
    result = run_one_cycle()
    print(f"\nSELF_IMPROVE_SUMMARY={json.dumps(result)}")
