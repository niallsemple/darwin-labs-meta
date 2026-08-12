"""DARWIN Meta-Engine — Steering Committee

The daily K3 check.  This script:
1. Collects the last 24h of work (git diff, board reports, meta-reports)
2. Packages it into a concise briefing
3. Asks Kimi K3 (via API) for strategic steering
4. Writes the steering response to reports/ for human review

This is the 'once a day' check that prevents the system from
building the wrong thing.
"""

from __future__ import annotations

import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
K3_API_KEY = os.environ.get("KIMI_API_KEY", "")
K3_BASE_URL = os.environ.get("KIMI_BASE_URL", "https://api.moonshot.cn/v1")


def git_log_since(hours: int = 24) -> str:
    since = f"{hours}.hours"
    result = subprocess.run(
        ["git", "log", f"--since={since}", "--pretty=format:%h %s", "--no-merges"],
        cwd=ROOT, capture_output=True, text=True, timeout=30,
    )
    return result.stdout.strip()


def latest_reports(n: int = 3) -> str:
    lines = []
    for f in sorted((ROOT / "reports").glob("*.md"), reverse=True)[:n]:
        lines.append(f"--- {f.name} ---")
        lines.append(f.read_text()[:800])
    return "\n".join(lines)


def call_k3(briefing: str) -> str:
    import urllib.request
    payload = {
        "model": "kimi-k3",
        "messages": [
            {"role": "system", "content": (
                "You are the DARWIN Steering Committee. Your job is to review the last 24h "
                "of autonomous lab work and provide ONE strategic course-correction if needed. "
                "Be concise. If everything looks healthy, say so. If the system is drifting, "
                "name the drift and suggest a specific fix."
            )},
            {"role": "user", "content": briefing},
        ],
        "temperature": 0.2,
        "max_tokens": 1024,
    }
    req = urllib.request.Request(
        f"{K3_BASE_URL}/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {K3_API_KEY}"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        result = json.loads(resp.read().decode("utf-8"))
    return result["choices"][0]["message"]["content"]


def main() -> None:
    if not K3_API_KEY:
        print("WARNING: KIMI_API_KEY not set. Steering committee cannot call K3.")
        print("Set it with: export KIMI_API_KEY=your_key")
        return

    git_changes = git_log_since(24)
    reports = latest_reports(3)

    briefing = (
        "## Last 24h Git Activity\n" + (git_changes or "No commits.") + "\n\n"
        "## Recent Reports\n" + reports + "\n\n"
        "Please provide a brief steering assessment."
    )

    print("Calling K3 Steering Committee...")
    try:
        steering = call_k3(briefing)
    except Exception as e:
        steering = f"Steering call failed: {e}"

    out_path = ROOT / "reports" / f"steering-{datetime.now(timezone.utc).strftime('%Y-%m-%d')}.md"
    out_path.write_text(f"# Steering Committee — {datetime.now(timezone.utc).strftime('%Y-%m-%d')}\n\n{steering}\n")
    print(f"Steering report: {out_path}")


if __name__ == "__main__":
    main()
