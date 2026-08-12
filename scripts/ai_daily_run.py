"""DARWIN Meta-Engine — Daily AI Run

Orchestrates the full AI pipeline:\n
1. Check local LLM health\n
2. Run AI board meeting (agents analyse library)\n
3. Update meta-learning loop\n
4. Write meta-report\n
5. Git commit\n
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


def sh(cmd: list[str]) -> tuple[int, str]:
    p = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, timeout=1200)
    return p.returncode, (p.stdout + p.stderr)


def main() -> None:
    summary = {"steps": {}, "timestamp": datetime.now(timezone.utc).isoformat()}

    # 1. Health check
    llm = LLMBridge()
    if not llm.health():
        print("FATAL: Local LLM server not responding at", llm.base_url)
        print("Start it with: ./start-server.sh")
        sys.exit(1)
    summary["steps"]["llm_health"] = {"status": "ok"}
    print("LLM health: OK")

    # 2. AI Board Meeting
    try:
        report_path = ROOT / "reports" / f"board-ai-{datetime.now(timezone.utc).strftime('%Y-%m-%d')}.md"
        text = generate_ai_boardMeeting(
            ROOT / "library" / "edges.json",
            ROOT / "library" / "graveyard.json",
            report_path,
            llm=llm,
        )
        summary["steps"]["ai_board_meeting"] = {"status": "ok", "report": str(report_path)}
        print(f"AI Board Meeting: {report_path}")
    except Exception as e:
        summary["steps"]["ai_board_meeting"] = {"status": "error", "error": str(e)}
        print(f"AI Board Meeting failed: {e}")

    # 3. Meta-learning report
    try:
        loop = MetaLearningLoop()
        meta_report = loop.render_report_md()
        meta_path = ROOT / "reports" / f"meta-{datetime.now(timezone.utc).strftime('%Y-%m-%d')}.md"
        meta_path.write_text(meta_report)
        summary["steps"]["meta_report"] = {"status": "ok", "report": str(meta_path)}
        print(f"Meta report: {meta_path}")
    except Exception as e:
        summary["steps"]["meta_report"] = {"status": "error", "error": str(e)}
        print(f"Meta report failed: {e}")

    # 4. Git commit
    rc, out = sh(["git", "add", "-A"])
    rc2, out2 = sh(["git", "-c", "user.name=darwin-meta",
                    "-c", "user.email=darwin@local",
                    "commit", "-qm",
                    f"ai-daily-run: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')} UTC"])
    committed = rc2 == 0 and "nothing to commit" not in out2.lower()
    summary["steps"]["git"] = {"committed": committed}
    print("Git:", "committed" if committed else "nothing to commit")

    # 5. Summary
    print(f"\nDARWIN_AI_SUMMARY={json.dumps(summary)}")


if __name__ == "__main__":
    main()
