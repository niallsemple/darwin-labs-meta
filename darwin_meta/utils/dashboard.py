"""DARWIN Meta-Engine — Dashboard Generator

Generates a self-contained HTML dashboard from the library, graveyard,
agent logs, and decay reports. No external dependencies — pure HTML/CSS/JS.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from collections import Counter


DASHBOARD_TEMPLATE = '''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>DARWIN Labs — Live Dashboard</title>
<style>
  :root {{
    --bg: #0d1117; --card: #161b22; --border: #30363d;
    --text: #c9d1d9; --muted: #8b949e; --accent: #58a6ff;
    --green: #3fb950; --red: #f85149; --yellow: #d29922; --orange: #e3b341;
  }}
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: -apple-system,BlinkMacSystemFont,"Segoe UI",Helvetica,Arial,sans-serif;
         background: var(--bg); color: var(--text); line-height: 1.5; }}
  header {{ padding: 1.5rem 2rem; border-bottom: 1px solid var(--border); }}
  header h1 {{ font-size: 1.5rem; display: flex; align-items: center; gap: 0.5rem; }}
  header .timestamp {{ color: var(--muted); font-size: 0.85rem; margin-top: 0.25rem; }}
  .container {{ max-width: 1400px; margin: 0 auto; padding: 1.5rem 2rem; }}
  .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 1rem; margin-bottom: 1.5rem; }}
  .card {{ background: var(--card); border: 1px solid var(--border); border-radius: 8px; padding: 1rem; }}
  .card h3 {{ font-size: 0.875rem; text-transform: uppercase; letter-spacing: 0.05em; color: var(--muted); margin-bottom: 0.75rem; }}
  .stat {{ font-size: 2rem; font-weight: 600; }}
  .stat.small {{ font-size: 1.25rem; }}
  .tag {{ display: inline-block; padding: 0.15rem 0.5rem; border-radius: 12px; font-size: 0.75rem; font-weight: 500; }}
  .tag.candidate {{ background: #1f6feb33; color: var(--accent); }}
  .tag.testing {{ background: #d2992233; color: var(--yellow); }}
  .tag.supported {{ background: #3fb95033; color: var(--green); }}
  .tag.validated {{ background: #a371f733; color: #a371f7; }}
  .tag.shadow {{ background: #79c0ff33; color: #79c0ff; }}
  .tag.killed {{ background: #f8514933; color: var(--red); }}
  table {{ width: 100%; border-collapse: collapse; font-size: 0.875rem; }}
  th, td {{ padding: 0.5rem; text-align: left; border-bottom: 1px solid var(--border); }}
  th {{ color: var(--muted); font-weight: 500; }}
  tr:hover {{ background: #21262d; }}
  .progress-bar {{ height: 6px; background: var(--border); border-radius: 3px; overflow: hidden; margin-top: 0.25rem; }}
  .progress-bar > div {{ height: 100%; border-radius: 3px; }}
  .health-good {{ color: var(--green); }} .health-warn {{ color: var(--yellow); }} .health-bad {{ color: var(--red); }}
  .section {{ margin-bottom: 2rem; }}
  .section h2 {{ font-size: 1.1rem; margin-bottom: 0.75rem; display: flex; align-items: center; gap: 0.5rem; }}
</style>
</head>
<body>
<header>
  <h1>🧬 DARWIN Labs — Live Dashboard</h1>
  <div class="timestamp">Generated: {timestamp}</div>
</header>
<div class="container">

  <div class="grid">
    <div class="card">
      <h3>Live Discoveries</h3>
      <div class="stat">{live_count}</div>
    </div>
    <div class="card">
      <h3>Graveyard</h3>
      <div class="stat">{graveyard_count}</div>
    </div>
    <div class="card">
      <h3>Survival Rate</h3>
      <div class="stat">{survival_rate}</div>
      <div class="progress-bar"><div style="width:{survival_pct}%;background:var(--green)"></div></div>
    </div>
    <div class="card">
      <h3>Agent Runs (24h)</h3>
      <div class="stat">{agent_runs_24h}</div>
    </div>
  </div>

  <div class="section">
    <h2>📊 Status Breakdown</h2>
    <div class="grid">
      {status_cards}
    </div>
  </div>

  <div class="section">
    <h2>🔬 Live Discoveries</h2>
    <table>
      <thead><tr><th>ID</th><th>Title</th><th>Lab</th><th>Status</th><th>Effect</th><th>n</th><th>p-value</th></tr></thead>
      <tbody>
        {live_rows}
      </tbody>
    </table>
  </div>

  <div class="section">
    <h2>⚰️ Recent Graveyard</h2>
    <table>
      <thead><tr><th>ID</th><th>Title</th><th>Lab</th><th>Kill Cause</th></tr></thead>
      <tbody>
        {grave_rows}
      </tbody>
    </table>
  </div>

  <div class="section">
    <h2>📉 Decay Signals</h2>
    {decay_section}
  </div>

  <div class="section">
    <h2>🤖 Agent Performance (Last 50 Runs)</h2>
    <table>
      <thead><tr><th>Agent</th><th>Runs</th><th>Success</th><th>Avg Latency</th><th>Health</th></tr></thead>
      <tbody>
        {agent_rows}
      </tbody>
    </table>
  </div>

</div>
</body>
</html>
'''


def _status_card(status: str, count: int, total: int) -> str:
    pct = count / total * 100 if total else 0
    color = {
        "CANDIDATE": "candidate", "TESTING": "testing",
        "SUPPORTED": "supported", "VALIDATED": "validated",
        "SHADOW": "shadow", "MICRO_LIVE": "supported",
        "PROMOTED": "validated", "KILLED": "killed",
    }.get(status, "candidate")
    return f'''<div class="card">
      <div style="display:flex;justify-content:space-between;align-items:center">
        <span class="tag {color}">{status}</span>
        <span style="font-size:1.5rem;font-weight:600">{count}</span>
      </div>
      <div class="progress-bar"><div style="width:{pct:.0f}%;background:var(--{'green' if status in ('SUPPORTED','VALIDATED','PROMOTED') else 'yellow' if status in ('TESTING','SHADOW') else 'red'})"></div></div>
    </div>'''


def _live_row(d: dict) -> str:
    m = d.get("metrics", {})
    status = d["status"]
    color = {"SUPPORTED": "supported", "VALIDATED": "validated", "SHADOW": "shadow",
             "TESTING": "testing", "CANDIDATE": "candidate"}.get(status, "candidate")
    effect = f"{m.get('effect_size', '-')} {m.get('effect_unit', '')}" if m.get("effect_size") is not None else "—"
    p = f"{m.get('p_value', '-'):.4f}" if m.get("p_value") is not None else "—"
    return f'<tr><td><code>{d["id"]}</code></td><td>{d["title"][:50]}</td><td>{d["lab"]}</td><td><span class="tag {color}">{status}</span></td><td>{effect}</td><td>{m.get("n", "—")}</td><td>{p}</td></tr>'


def _grave_row(d: dict) -> str:
    return f'<tr><td><code>{d["id"]}</code></td><td>{d["title"][:50]}</td><td>{d["lab"]}</td><td>{d.get("kill_cause", "unknown")[:80]}</td></tr>'


def _agent_rows(meta_logs: list[dict]) -> str:
    if not meta_logs:
        return '<tr><td colspan="5" style="text-align:center;color:var(--muted)">No agent logs yet</td></tr>'
    rows = []
    by_agent = {}
    for log in meta_logs:
        agent = log.get("agent", "unknown")
        if agent not in by_agent:
            by_agent[agent] = []
        by_agent[agent].append(log)
    for agent, logs in sorted(by_agent.items()):
        total = len(logs)
        success = sum(1 for l in logs if l.get("success", True))
        avg_lat = sum(l.get("latency_ms", 0) for l in logs) / total if total else 0
        health_class = "health-good" if success / total >= 0.9 else "health-warn" if success / total >= 0.7 else "health-bad"
        rows.append(f'<tr><td>{agent}</td><td>{total}</td><td class="{health_class}">{success}/{total} ({success/total*100:.0f}%)</td><td>{avg_lat:.0f}ms</td><td class="{health_class}">{"✓" if success/total >= 0.9 else "⚠" if success/total >= 0.7 else "✗"}</td></tr>')
    return "\n".join(rows)


def generate_dashboard(library_path: Path, graveyard_path: Path,
                       meta_log_path: Path | None,
                       decay_reports: list | None,
                       out_path: Path) -> str:
    lib = json.loads(library_path.read_text()) if library_path.exists() else []
    grave = json.loads(graveyard_path.read_text()) if graveyard_path.exists() else []
    logs = []
    if meta_log_path and meta_log_path.exists():
        for line in meta_log_path.read_text().strip().split("\n"):
            if line:
                try:
                    logs.append(json.loads(line))
                except json.JSONDecodeError:
                    pass

    # Recent logs only (last 50)
    recent_logs = logs[-50:]

    live_count = len(lib)
    grave_count = len(grave)
    total = live_count + grave_count
    survival_rate = f"{live_count / total:.1%}" if total else "N/A"
    survival_pct = live_count / total * 100 if total else 0

    # 24h agent runs
    from datetime import datetime, timezone, timedelta
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
    runs_24h = sum(1 for l in recent_logs if l.get("timestamp", "") > cutoff)

    # Status cards
    counts = Counter(d["status"] for d in lib)
    status_cards = "\n".join(_status_card(s, counts.get(s, 0), live_count) for s in
                              ["CANDIDATE", "TESTING", "SUPPORTED", "VALIDATED", "SHADOW", "MICRO_LIVE", "PROMOTED"])

    # Live rows
    live_rows = "\n".join(_live_row(d) for d in sorted(lib, key=lambda x: x["id"]))
    if not live_rows:
        live_rows = '<tr><td colspan="7" style="text-align:center;color:var(--muted)">No live discoveries</td></tr>'

    # Grave rows
    grave_rows = "\n".join(_grave_row(d) for d in grave[-10:])
    if not grave_rows:
        grave_rows = '<tr><td colspan="4" style="text-align:center;color:var(--muted)">Graveyard empty</td></tr>'

    # Decay section
    if decay_reports:
        decay_lines = []
        for r in sorted(decay_reports, key=lambda x: x.decay_score, reverse=True):
            emoji = {"healthy": "🟢", "watch": "🟡", "investigate": "🟠", "escalate": "🔴"}.get(r.recommendation, "⚪")
            decay_lines.append(f'<div class="card"><div style="display:flex;justify-content:space-between"><strong>{r.discovery_id}</strong><span class="tag {r.recommendation}">{emoji} {r.recommendation.upper()}</span></div><div style="color:var(--muted);font-size:0.8rem;margin-top:0.25rem">{r.title}</div><div style="margin-top:0.5rem">{"; ".join(r.signals)}</div></div>')
        decay_section = "\n".join(decay_lines)
    else:
        decay_section = '<p style="color:var(--muted)">No decay signals detected.</p>'

    # Agent rows
    agent_rows = _agent_rows(recent_logs)

    html = DASHBOARD_TEMPLATE.format(
        timestamp=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        live_count=live_count,
        graveyard_count=grave_count,
        survival_rate=survival_rate,
        survival_pct=survival_pct,
        agent_runs_24h=runs_24h,
        status_cards=status_cards,
        live_rows=live_rows,
        grave_rows=grave_rows,
        decay_section=decay_section,
        agent_rows=agent_rows,
    )

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(html)
    return str(out_path)


if __name__ == "__main__":
    import sys
    root = Path(__file__).resolve().parent.parent.parent
    path = generate_dashboard(
        root / "library" / "edges.json",
        root / "library" / "graveyard.json",
        root / "darwin_meta" / "loops" / "agent_performance.jsonl",
        None,
        root / "reports" / "dashboard.html",
    )
    print(f"Dashboard: {path}")
