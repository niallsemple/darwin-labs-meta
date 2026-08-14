"""DARWIN Meta-Engine — AI Board Meeting

Replaces the static markdown generator with one that actually uses
agents to analyse the library and produce a strategic daily report.
Now includes Archaeologist (institutional memory) and Decay Detection.
"""

from __future__ import annotations

import json
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from darwin_meta.agents.ceo import CEOAgent
from darwin_meta.agents.statistician import StatisticianAgent
from darwin_meta.agents.sceptic import ScepticAgent
from darwin_meta.agents.archaeologist import ArchaeologistAgent
from darwin_meta.loops.decay_detection import scan_library, render_decay_report
from laboratory.experiment import results_for_discovery, latest_metrics

ROOT = Path(__file__).resolve().parent.parent


def _verified_data_summary(d: dict) -> str:
    """Assemble the VERIFIED numbers for a discovery: immutable experiment
    results first, library metrics second (labelled unverified), evidence
    notes last. The Statistician critiques these — it never invents them."""
    lines = []
    results = results_for_discovery(d["id"])
    if results:
        lines.append(f"EXPERIMENT RESULTS (immutable store, {len(results)} run(s)):")
        for r in results[-3:]:
            m = r.get("metrics", {})
            lines.append(
                f"  result {r.get('result_hash')} (spec {r.get('spec_hash')}, "
                f"{r.get('created', '?')[:10]}): "
                + ", ".join(f"{k}={v}" for k, v in m.items()))
    else:
        lines.append("EXPERIMENT RESULTS: none — no deterministic experiment "
                     "has been recorded for this discovery.")

    m = d.get("metrics", {})
    if any(v is not None for v in m.values()):
        lines.append("LIBRARY METRICS (self-reported, UNVERIFIED):")
        lines.append("  " + ", ".join(f"{k}={v}" for k, v in m.items()
                                       if v is not None and v != ""))
    ev = d.get("evidence", [])
    if ev:
        lines.append("EVIDENCE NOTES (latest 3):")
        for e in ev[-3:]:
            lines.append(f"  [{e.get('kind')}] {e.get('author')}: {e.get('note', '')[:200]}")
    lines.append("Your job: critique whether these numbers are believable "
                 "(sample size, leakage, multiple testing, regimes). "
                 "Do NOT calculate new statistics.")
    return "\n".join(lines)


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
                             out_path: Path, llm=None,
                             meta_log_path: Path | None = None,
                             returns_source: dict | None = None) -> str:
    """Run the full AI pipeline to produce a board meeting report.

    Args:
        library_path: Path to edges.json
        graveyard_path: Path to graveyard.json
        out_path: Where to write the markdown report
        llm: LLMBridge instance
        meta_log_path: Optional path to agent_performance.jsonl for Archaeologist
        returns_source: Optional mapping of discovery_id -> recent daily returns for decay detection
    """
    lib = json.loads(library_path.read_text()) if library_path.exists() else []
    grave = json.loads(graveyard_path.read_text()) if graveyard_path.exists() else []

    today = datetime.now(timezone.utc).strftime("%d %B %Y").upper()

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

    # --- DECAY DETECTION (deterministic, no LLM) ---
    print("  [Decay] Scanning for decay signals...", flush=True)
    decay_reports = scan_library(library_path, returns_source)
    decay_md = render_decay_report(decay_reports)
    print(f"    → {len(decay_reports)} discoveries showing decay", flush=True)

    # --- ARCHAEOLOGIST (institutional memory) ---
    print("  [Archaeologist] Mining lab history...", flush=True)
    archaeologist_notes = []
    try:
        arch_agent = ArchaeologistAgent(llm)
        arch_report = arch_agent.run(lib, grave)
        if arch_report.get("recurring_failures"):
            archaeologist_notes.append("**Recurring failure patterns:**")
            for rf in arch_report["recurring_failures"][:3]:
                archaeologist_notes.append(f"- {rf['pattern']} ({rf['count']} times)")
        if arch_report.get("institutional_notes"):
            archaeologist_notes.append("**Institutional notes:**")
            for note in arch_report["institutional_notes"][:3]:
                archaeologist_notes.append(f"- {note}")
        if arch_report.get("zombie_hypotheses"):
            archaeologist_notes.append("**Zombie hypotheses:**")
            for zh in arch_report["zombie_hypotheses"][:2]:
                archaeologist_notes.append(f"- '{zh['title_pattern']}' seen {zh['occurrences']} times")
        print("    → Archaeologist analysis complete", flush=True)
        time.sleep(2)
    except Exception as e:
        archaeologist_notes.append(f"Archaeologist error: {e}")
        print(f"    → ERROR: {e}", flush=True)

    # Run Statistician on each SUPPORTED+ discovery.
    # The Statistician receives VERIFIED data — experiment results from the
    # immutable store plus the record's metrics — and critiques believability.
    # It is never the source of statistical truth.
    stat_reports = []
    stat_agent = StatisticianAgent(llm)
    targets = [d for d in lib if d["status"] in ("SUPPORTED", "VALIDATED", "SHADOW")]
    for i, d in enumerate(targets, 1):
        ctx = _summarise_discovery(d)
        verified = _verified_data_summary(d)
        print(f"  [Statistician] {d['id']} ({i}/{len(targets)})...", flush=True)
        try:
            report = stat_agent.run(ctx, verified)
            stat_reports.append(f"{d['id']}: {report['verdict']} — {report['recommendation'][:100]}")
            print(f"    → {report['verdict']}", flush=True)
            time.sleep(2)
        except Exception as e:
            stat_reports.append(f"{d['id']}: stat error — {e}")
            print(f"    → ERROR: {e}", flush=True)

    # Run Sceptic on each SUPPORTED+ discovery
    scept_reports = []
    scept_agent = ScepticAgent(llm)
    for i, d in enumerate(targets, 1):
        ctx = _summarise_discovery(d)
        evidence = "\n".join(e["note"][:200] for e in d.get("evidence", [])[-3:])
        print(f"  [Sceptic] {d['id']} ({i}/{len(targets)})...", flush=True)
        try:
            report = scept_agent.run(ctx, evidence)
            scept_reports.append(
                f"{d['id']}: {report['verdict']} (kill_prob={report['kill_probability']:.2f}) — "
                f"top attack: {report['attacks'][0]['attack'][:80] if report['attacks'] else 'none'}"
            )
            print(f"    → {report['verdict']} (kill_prob={report['kill_probability']:.2f})", flush=True)
            time.sleep(2)
        except Exception as e:
            scept_reports.append(f"{d['id']}: sceptic error — {e}")
            print(f"    → ERROR: {e}", flush=True)

    # Run CEO synthesis
    print("  [CEO] Synthesising board meeting...", flush=True)
    ceo_agent = CEOAgent(llm)
    # Include Archaeologist insights in CEO briefing
    arch_section = "\n".join(archaeologist_notes) if archaeologist_notes else "No institutional notes."
    agent_reports = (
        "STATISTICIAN REPORTS:\n" + "\n".join(stat_reports) + "\n\n"
        "SCEPTIC REPORTS:\n" + "\n".join(scept_reports) + "\n\n"
        "DECAY REPORT:\n" + (f"{len(decay_reports)} discoveries showing decay signals. "
                              "Escalate if score > 0.7." if decay_reports else "No decay detected.") + "\n\n"
        "ARCHAEOLOGIST NOTES:\n" + arch_section
    )
    try:
        ceo_decision = ceo_agent.run("\n".join(lib_summary_lines), agent_reports)
        print("    → CEO synthesis complete", flush=True)
    except Exception as e:
        ceo_decision = {
            "agenda": [], "build_queue": [], "kill_queue": [],
            "investigate_queue": [], "ceo_commentary": f"CEO synthesis failed: {e}",
        }
        print(f"    → CEO ERROR: {e}", flush=True)

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

    if ceo_decision.get("investigate_queue"):
        L.append("## INVESTIGATE QUEUE")
        L.append("")
        for did in ceo_decision["investigate_queue"]:
            L.append(f"- `{did}`")
        L.append("")

    # Decay section
    if decay_reports:
        L.append("## DECAY ALERTS")
        L.append("")
        for r in sorted(decay_reports, key=lambda x: x.decay_score, reverse=True)[:5]:
            emoji = {"healthy": "🟢", "watch": "🟡", "investigate": "🟠", "escalate": "🔴"}.get(r.recommendation, "⚪")
            L.append(f"- {emoji} **{r.discovery_id}** — decay score {r.decay_score:.2f} ({r.recommendation})")
            for sig in r.signals:
                L.append(f"  - {sig}")
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

    if archaeologist_notes:
        L.append("## ARCHAEOLOGIST NOTES")
        L.append("")
        for note in archaeologist_notes:
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
