"""DARWIN Meta-Engine — AI Board Meeting

Replaces the static markdown generator with one that actually uses
agents to analyse the library and produce a strategic daily report.
"""

from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from darwin_meta.agents.ceo import CEOAgent
from darwin_meta.agents.statistician import StatisticianAgent
from darwin_meta.agents.sceptic import ScepticAgent

ROOT = Path(__file__).resolve().parent.parent


def _summarise_discovery(d: dict) -> str:
    lines = [
        f"ID: {d['id']} — {d['title']}",
        f"  Lab: {d['lab']} | Status: {d['status']}",
        f"  Hypothesis: {d.get('hypothesis', '')[:120]}",
        f"  Gates: S={d['gates']['sceptic']} St={d['gates']['statistician']} "
        f"E={d['gates']['execution']} R={d['gates']['risk']}",
    ]
    m = d.get("metrics", {})
    if m.get("effect_size") is not None:
        lines.append(f"  Effect: {m['effect_size']}{m.get('effect_unit', '')}  n={m.get('n')}  p={m.get('p_value')}")
    lines.append(f"  Evidence entries: {len(d.get('evidence', []))}")
    return "\n".join(lines)


def generate_ai_boardMeeting(library_path: Path, graveyard_path: Path,
                             out_path: Path, llm=None) -> str:
    """Run the full AI pipeline to produce a board meeting report."""
    lib = json.loads(library_path.read_text()) if library_path.exists() else []
    grave = json.loads(graveyard_path.read_text()) if graveyard_path.exists() else []

    today = datetime.now(timezone.utc).strftime("%d %B %Y").upper()
    today_iso = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    counts = Counter(d["status"] for d in lib)

    # Build library summary for CEO
    lib_summary_lines = [
        f"Total live discoveries: {len(lib)}",
        f"Total graveyard: {len(grave)}",
        "Status breakdown:",
    ]
    for s in ["CANDIDATE", "TESTING", "SUPPORTED", "VALIDATED", "SHADOW",
              "MICRO_LIVE", "PROMOTED"]:
        if counts.get(s):
            lib_summary_lines.append(f"  {s}: {counts[s]}")

    # Run Statistician on each SUPPORTED+ discovery
    stat_reports = []
    stat_agent = StatisticianAgent(llm)
    for d in lib:
        if d["status"] in ("SUPPORTED", "VALIDATED", "SHADOW"):
            ctx = _summarise_discovery(d)
            try:
                report = stat_agent.run(ctx, "See evidence in library record.")
                stat_reports.append(f"{d['id']}: {report['verdict']} — {report['recommendation'][:100]}")
            except Exception as e:
                stat_reports.append(f"{d['id']}: stat error — {e}")

    # Run Sceptic on each SUPPORTED+ discovery
    scept_reports = []
    scept_agent = ScepticAgent(llm)
    for d in lib:
        if d["status"] in ("SUPPORTED", "VALIDATED", "SHADOW"):
            ctx = _summarise_discovery(d)
            evidence = "\n".join(e["note"][:200] for e in d.get("evidence", [])[-3:])
            try:
                report = scept_agent.run(ctx, evidence)
                scept_reports.append(
                    f"{d['id']}: {report['verdict']} (kill_prob={report['kill_probability']:.2f}) — "
                    f"top attack: {report['attacks'][0]['attack'][:80] if report['attacks'] else 'none'}"
                )
            except Exception as e:
                scept_reports.append(f"{d['id']}: sceptic error — {e}")

    # Run CEO synthesis
    ceo_agent = CEOAgent(llm)
    agent_reports = (
        "STATISTICIAN REPORTS:\n" + "\n".join(stat_reports) + "\n\n"
        "SCEPTIC REPORTS:\n" + "\n".join(scept_reports)
    )
    try:
        ceo_decision = ceo_agent.run("\n".join(lib_summary_lines), agent_reports)
    except Exception as e:
        ceo_decision = {
            "agenda": [], "build_queue": [], "kill_queue": [],
            "investigate_queue": [], "ceo_commentary": f"CEO synthesis failed: {e}",
        }

    # Render markdown
    L = []
    L.append("# DARWIN DAILY BOARD MEETING — AI EDITION")
    L.append(f"## {today}")
    L.append("")
    L.append("```")
    L.append(f"library: {len(lib)} live discoveries   graveyard: {len(grave)} killed")
    for s in ["CANDIDATE", "TESTING", "SUPPORTED", "VALIDATED", "SHADOW",
              "MICRO_LIVE", "PROMOTED"]:
        if counts.get(s):
            L.append(f"  {s:<12} {counts[s]}")
    L.append("```")
    L.append("")

    L.append("## CEO COMMENTARY")
    L.append("")
    L.append(ceo_decision.get("ceo_commentary", "No commentary generated."))
    L.append("")

    if ceo_decision.get("agenda"):
        L.append("## TODAY'S AGENDA")
        L.append("")
        for item in ceo_decision["agenda"]:
            L.append(f"- **{item['action']}** `{item['target_id']}` — {item['rationale']}")
        L.append("")

    if ceo_decision.get("build_queue"):
        L.append("## BUILD QUEUE")
        L.append("")
        for did in ceo_decision["build_queue"]:
            L.append(f"- `{did}`")
        L.append("")

    if ceo_decision.get("kill_queue"):
        L.append("## KILL QUEUE")
        L.append("")
        for did in ceo_decision["kill_queue"]:
            L.append(f"- `{did}`")
        L.append("")

    if stat_reports:
        L.append("## STATISTICIAN NOTES")
        L.append("")
        for note in stat_reports:
            L.append(f"- {note}")
        L.append("")

    if scept_reports:
        L.append("## SCEPTIC ATTACKS")
        L.append("")
        for note in scept_reports:
            L.append(f"- {note}")
        L.append("")

    if grave:
        L.append("## GRAVEYARD (recent)")
        L.append("")
        for d in grave[-5:]:
            L.append(f"- **{d['id']}** {d['title']}")
            L.append(f"  KILLED: {d.get('kill_cause', 'unknown')}")
        L.append("")

    L.append("---")
    L.append("*This report was generated by the DARWIN Meta-Engine. "
             "Human review required before any status transitions.*")

    text = "\n".join(L) + "\n"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(text)
    return text


if __name__ == "__main__":
    import sys
    generate_ai_boardMeeting(
        ROOT / "library" / "edges.json",
        ROOT / "library" / "graveyard.json",
        ROOT / "reports" / f"board-ai-{datetime.now(timezone.utc).strftime('%Y-%m-%d')}.md",
    )
