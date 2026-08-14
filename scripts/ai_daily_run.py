"""DARWIN Meta-Engine — Daily AI Run

Orchestrates the full AI pipeline:
1. Check local LLM health
2. Run decay detection (deterministic, fed with real returns)
3. Autonomous discovery loop (deterministic anomaly scan -> Explorer frames
   hypotheses -> new CANDIDATEs enter the library)
4. Run AI board meeting (agents analyse library)
5. Generate HTML dashboard
6. Update meta-learning loop + write meta-report
7. Self-Improvement cycle — SANDBOXED: implementations happen on a
   self-improve/* branch and leave as a pull request; main is untouched
8. Git commit + push (daily reports only, on the current branch)

Usage: python3 scripts/ai_daily_run.py
"""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from darwin_meta.utils.llm_bridge import LLMBridge
from darwin_meta.ai_board_meeting import generate_ai_boardMeeting
from darwin_meta.loops.meta_learning import MetaLearningLoop
from darwin_meta.loops.decay_detection import scan_library, render_decay_report
from darwin_meta.utils.dashboard import generate_dashboard
from darwin_meta.self_improve.loop import run_one_cycle as run_self_improve


def sh(cmd: list[str], timeout: int = 120) -> tuple[int, str]:
    p = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, timeout=timeout)
    return p.returncode, (p.stdout + p.stderr)


def main() -> None:
    summary = {"steps": {}, "timestamp": datetime.now(timezone.utc).isoformat()}

    # 1. Health check
    llm = LLMBridge()
    healthy = llm.health()
    summary["steps"]["llm_health"] = {"status": "ok" if healthy else "degraded"}
    print("LLM health:", "OK" if healthy else "DEGRADED (will try anyway)")
    if not healthy:
        print("WARNING: LLM not responding. Board meeting may fail.")

    # 2. Decay detection (deterministic, no LLM needed) — fed with REAL returns
    try:
        from darwin_meta.utils.returns_adapter import build_returns_source
        returns_source, returns_prov = build_returns_source(ROOT / "library" / "returns_sources.json")
        decay_reports = scan_library(ROOT / "library" / "edges.json", returns_source)
        decay_path = ROOT / "reports" / f"decay-{datetime.now(timezone.utc).strftime('%Y-%m-%d')}.md"
        decay_path.write_text(render_decay_report(decay_reports))
        summary["steps"]["decay_detection"] = {
            "status": "ok",
            "reports": len(decay_reports),
            "report_path": str(decay_path),
            "returns_provenance": returns_prov,
        }
        print(f"Decay detection: {len(decay_reports)} signals → {decay_path}")
        for did, prov in returns_prov.items():
            print(f"  returns[{did}]: {prov}")
    except Exception as e:
        summary["steps"]["decay_detection"] = {"status": "error", "error": str(e)}
        print(f"Decay detection failed: {e}")
        decay_reports = []
        returns_source = None

    # 3. Autonomous Discovery Loop (deterministic scan; LLM frames hypotheses)
    try:
        from darwin_meta.discovery.loop import run_discovery_loop
        disc = run_discovery_loop(llm=llm, max_new_candidates=3)
        summary["steps"]["discovery"] = {
            "status": "ok",
            "tests_run": disc["tests_run"],
            "fdr_survivors": disc["fdr_survivors"],
            "new_candidates": len(disc["new_candidates"]),
            "skipped_duplicates": disc["skipped_duplicates"],
        }
        print(f"Discovery: {disc['tests_run']} tests, {disc['fdr_survivors']} FDR survivors, "
              f"{len(disc['new_candidates'])} new candidates")
    except Exception as e:
        summary["steps"]["discovery"] = {"status": "error", "error": str(e)}
        print(f"Discovery loop failed: {e}")

    # 4. AI Board Meeting
    try:
        report_path = ROOT / "reports" / f"board-ai-{datetime.now(timezone.utc).strftime('%Y-%m-%d')}.md"
        text = generate_ai_boardMeeting(
            ROOT / "library" / "edges.json",
            ROOT / "library" / "graveyard.json",
            report_path,
            llm=llm,
            meta_log_path=ROOT / "darwin_meta" / "loops" / "agent_performance.jsonl",
            returns_source=returns_source,
        )
        summary["steps"]["ai_board_meeting"] = {"status": "ok", "report": str(report_path)}
        print(f"AI Board Meeting: {report_path}")
    except Exception as e:
        summary["steps"]["ai_board_meeting"] = {"status": "error", "error": str(e)}
        print(f"AI Board Meeting failed: {e}")
        decay_reports = []

    # 5. Dashboard generation
    try:
        dash_path = generate_dashboard(
            ROOT / "library" / "edges.json",
            ROOT / "library" / "graveyard.json",
            ROOT / "darwin_meta" / "loops" / "agent_performance.jsonl",
            decay_reports,
            ROOT / "reports" / "dashboard.html",
        )
        summary["steps"]["dashboard"] = {"status": "ok", "path": dash_path}
        print(f"Dashboard: {dash_path}")
    except Exception as e:
        summary["steps"]["dashboard"] = {"status": "error", "error": str(e)}
        print(f"Dashboard failed: {e}")

    # 6. Meta-learning: attribute real outcomes to agent decisions, THEN adapt
    try:
        from darwin_meta.loops.outcome_attribution import attribute_outcomes, render_outcome_md
        outcome_res = attribute_outcomes()
        loop = MetaLearningLoop()
        if outcome_res["scores"]:
            loop.ingest_outcomes(outcome_res["scores"])  # real outcomes now drive prompt evolution
        meta_report = loop.render_report_md() + "\n" + render_outcome_md(outcome_res)
        meta_path = ROOT / "reports" / f"meta-{datetime.now(timezone.utc).strftime('%Y-%m-%d')}.md"
        meta_path.write_text(meta_report)
        summary["steps"]["meta_report"] = {
            "status": "ok", "report": str(meta_path),
            "outcome_agents": {a: s["avg_score"] for a, s in outcome_res["agents"].items()},
        }
        print(f"Meta report: {meta_path} "
              f"({len(outcome_res['agents'])} agents scored on real outcomes)")
    except Exception as e:
        summary["steps"]["meta_report"] = {"status": "error", "error": str(e)}
        print(f"Meta report failed: {e}")

    # 7. Self-Improvement Cycle (sandboxed: branch + PR, never main)
    try:
        si_summary = run_self_improve(llm=llm, max_repos=2, min_confidence=0.75, max_implementations=1)
        summary["steps"]["self_improve"] = {
            "status": "ok",
            "repos_evaluated": si_summary.get("repos_evaluated", 0),
            "approved": len(si_summary.get("approved", [])),
            "implemented": len(si_summary.get("implemented", [])),
        }
        print(f"Self-improve: {si_summary['repos_evaluated']} evaluated, "
              f"{len(si_summary['approved'])} approved, {len(si_summary['implemented'])} implemented")
    except Exception as e:
        summary["steps"]["self_improve"] = {"status": "error", "error": str(e)}
        print(f"Self-improve failed: {e}")

    # 8. Git commit + push
    rc, out = sh(["git", "add", "-A"])
    rc2, out2 = sh(["git", "-c", "user.name=darwin-meta",
                    "-c", "user.email=darwin@local",
                    "commit", "-qm",
                    f"ai-daily-run: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')} UTC"])
    committed = rc2 == 0 and "nothing to commit" not in out2.lower()
    summary["steps"]["git"] = {"committed": committed}
    print("Git:", "committed" if committed else "nothing to commit")

    # Push to origin (best effort)
    rc3, out3 = sh(["git", "push"])
    pushed = rc3 == 0
    summary["steps"]["git"]["pushed"] = pushed
    if pushed:
        print("Git: pushed to origin")
    else:
        print("Git: push skipped or failed:", out3[:200])

    # 9. Summary
    print(f"\nDARWIN_AI_SUMMARY={json.dumps(summary)}")


if __name__ == "__main__":
    main()
