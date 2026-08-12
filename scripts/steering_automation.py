"""DARWIN Steering Committee — Automation Runner

This script is called by the Blueprint Automation daily.
It collects the last 24h of work and calls Kimi K3 for steering.
"""

import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REPORTS_DIR = ROOT / "reports"
REPORTS_DIR.mkdir(parents=True, exist_ok=True)


def git_log_since(hours: int = 24) -> str:
    since = f"{hours}.hours"
    result = subprocess.run(
        ["git", "log", f"--since={since}", "--pretty=format:%h %s", "--no-merges"],
        cwd=ROOT, capture_output=True, text=True, timeout=30,
    )
    return result.stdout.strip()


def latest_reports(n: int = 3) -> str:
    lines = []
    report_files = sorted(REPORTS_DIR.glob("*.md"), reverse=True)
    for f in report_files[:n]:
        lines.append(f"--- {f.name} ---")
        lines.append(f.read_text()[:800])
    return "\n".join(lines)


def call_k3(briefing: str, api_key: str, base_url: str) -> str:
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
        f"{base_url}/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        result = json.loads(resp.read().decode("utf-8"))
    return result["choices"][0]["message"]["content"]


def main() -> dict:
    api_key = os.environ.get("KIMI_API_KEY", "")
    base_url = os.environ.get("KIMI_BASE_URL", "https://api.moonshot.cn/v1")

    if not api_key:
        return {"error": "KIMI_API_KEY not set"}

    git_changes = git_log_since(24)
    reports = latest_reports(3)

    briefing = (
        "## Last 24h Git Activity\n" + (git_changes or "No commits.") + "\n\n"
        "## Recent Reports\n" + reports + "\n\n"
        "Please provide a brief steering assessment."
    )

    try:
        steering = call_k3(briefing, api_key, base_url)
    except Exception as e:
        steering = f"Steering call failed: {e}"

    out_path = REPORTS_DIR / f"steering-{datetime.now(timezone.utc).strftime('%Y-%m-%d')}.md"
    out_path.write_text(
        f"# Steering Committee — {datetime.now(timezone.utc).strftime('%Y-%m-%d')}\n\n{steering}\n"
    )

    return {
        "report_path": str(out_path),
        "steering_advice": steering,
    }


if __name__ == "__main__":
    artifact = main()
    # Blueprint expects AutomationOutput JSON
    print(json.dumps({"artifact": artifact}, ensure_ascii=False))
