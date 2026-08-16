"""DARWIN Meta-Engine — AI Board Meeting

Replaces the static markdown generator with one that actually uses
agents to analyse the library and produce a strategic daily report.
Now includes Archaeologist (institutional memory), Decay Detection,
and daily stale-CANDIDATE re-evaluation.
"""

from __future__ import annotations

import json
import time
from collections import Counter
from datetime import datetime, timezone, timedelta
from pathlib import Path

from darwin_meta.agents.ceo import CEOAgent
from darwin_meta.agents.statistician import StatisticianAgent
from darwin_meta.agents.sceptic import ScepticAgent
from darwin_meta.agents.archaeologist import ArchaeologistAgent
from darwin_meta.loops.decay_detection import scan_library, render_decay_report
from darwin_meta.loops.decision_log import log_decision
from laboratory.experiment import results_for_discovery, latest_metrics

ROOT = Path(__file__).resolve().parent.parent

# --- Stale-CANDIDATE detection (deterministic) ---
MAX_CANDIDATE_AGE_DAYS = 14
MAX_CANDIDATE_EVIDENCE_STALE_DAYS = 7


def _days_since(ts_str: str) -> int | None:
    """Return days since ISO timestamp, or None if unparseable."""
    try:
        ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
        return (datetime.now(timezone.utc) - ts).days
    except Exception:
        return None


def _stale_candidate_summary(lib: list[dict]) -> str:
    """Produce a deterministic stale-CANDIDATE report for the CEO.

    A CANDIDATE is flagged stale if any of:
    - Age > MAX_CANDIDATE_AGE_DAYS since creation with no status progress
    - No evidence added in MAX_CANDIDATE_EVIDENCE_STALE_DAYS days
    - Empty next_action (no defined work)
    - Evidence count == 0 (raw hypothesis, no work done)
    """
    lines = []
    candidates = [d for d in lib if d.get("status") == "CANDIDATE"]
    if not candidates:
        return "No CANDIDATEs in library."

    stale_ids = []
    for d in candidates:
        reasons = []
        age = _days_since(d.get("created", ""))
        if age is not None and age > MAX_CANDIDATE_AGE_DAYS:
            reasons.append(f"age {age}d > {MAX_CANDIDATE_AGE_DAYS}d")

        evidence = d.get("evidence", [])
        if evidence:
            last_ev = _days_since(evidence[-1].get("date", ""))
            if last_ev is not None and last_ev > MAX_CANDIDATE_EVIDENCE_STALE_DAYS:
                reasons.append(f"last evidence {last_ev}d ago")
        else:
            reasons.append("zero evidence")

        if not d.get("next_action", "").strip():
            reasons.append("empty next_action")

        if reasons:
            stale_ids.append(d["id"])
            lines.append(
                f"- {d['id']} ({d.get('lab', '?')}) — {', '.join(reasons)} | "
                f"evidence={len(evidence)} | age={age}d"
            )

    if not lines:
        return f"All {len(candidates)} CANDIDATEs are active (no stale signals)."

    header = f"STALE CANDIDATES ({len(stale_ids)}/{len(candidates)}):\n"
    footer = (
        f"\nRecommendation: demote {len(stale_ids)} stale CANDIDATE(s) to BACKLOG "
        f"to free WIP slots for active work."
    )
    return header + "\n".join(lines) + footer


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
    for s in ["BACKLOG", "CANDIDATE", "TESTING", "SUPPORTED", "VALIDATED", "SHADOW",
              "MICRO_LIVE", "PROMOTED"]:
        if counts.get(s):
            lib_summary_lines.append(f"  {s}: {counts[s]}")

    # --- STALE CANDIDATE DETECTION (deterministic, no LLM) ---
    print("  [Stale] Checking CANDIDATEs for staleness...", flush=True)
    stale_summary, stale_ids = _stale_candidate_summary(lib)
    print(f"    → {stale_summary.splitlines()[0] if stale_summary else 'no stale check'}", flush=True)

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
        if isinstance(arch_report, dict):
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
        else:
            archaeologist_notes.append(f"Archaeologist returned unexpected type: {type(arch_report).__name__}")
        print("    → Archaeologist analysis complete", flush=True)
    except Exception as e:
        archaeologist_notes.append(f"Archaeologist error: {e}")
        print(f"    → ERROR: {e}", flush=True)

    # Run Statistician on each SUPPORTED+ discovery.
    stat_reports = []
    stat_agent = StatisticianAgent(llm)
    targets = [d for d in lib if d["status"] in ("SUPPORTED", "VALIDATED", "SHADOW")]
    for i, d in enumerate(targets, 1):
        ctx = _summarise_discovery(d)
        verified = _verified_data_summary(d)
        print(f"  [Statistician] {d['id']} ({i}/{len(targets)})...", flush=True)
        try:
            report = stat_agent.run(ctx, verified)
            if isinstance(report, dict):
                stat_reports.append(f"{d['id']}: {report.get('verdict', 'unknown')} — {str(report.get('recommendation', ''))[:100]}")
                log_decision("statistician", d["id"], report.get("verdict", "unknown"),
                             {"n": report.get("n"), "p_value": report.get("p_value"),
                              "concerns": report.get("concerns", [])[:3]})
                print(f"    → {report.get('verdict', 'unknown')}", flush=True)
            else:
                stat_reports.append(f"{d['id']}: stat type error — got {type(report).__name__}")
                print(f"    → TYPE ERROR: got {type(report).__name__}", flush=True)
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
            if isinstance(report, dict):
                verdict = report.get("verdict", "unknown")
                kp = report.get("kill_probability", 0.0)
                attacks = report.get("attacks", [])
                top = attacks[0].get("attack", "none")[:80] if attacks else "none"
                scept_reports.append(f"{d['id']}: {verdict} (kill_prob={kp:.2f}) — top attack: {top}")
                log_decision("sceptic", d["id"], verdict,
                             {"kill_probability": kp, "n_attacks": len(attacks)})
                print(f"    → {verdict} (kill_prob={kp:.2f})", flush=True)
            else:
                scept_reports.append(f"{d['id']}: sceptic type error — got {type(report).__name__}")
                print(f"    → TYPE ERROR: got {type(report).__name__}", flush=True)
        except Exception as e:
            scept_reports.append(f"{d['id']}: sceptic error — {e}")
            print(f"    → ERROR: {e}", flush=True)

    # Run CEO synthesis
    print("  [CEO] Synthesising board meeting...", flush=True)
    ceo_agent = CEOAgent(llm)
    arch_section = "\n".join(archaeologist_notes) if archaeologist_notes else "No institutional notes."
    agent_reports = (
        "STATISTICIAN REPORTS:\n" + "\n".join(stat_reports) + "\n\n"
        "SCEPTIC REPORTS:\n" + "\n".join(scept_reports) + "\n\n"
        "DECAY REPORT:\n" + (f"{len(decay_reports)} discoveries showing decay signals. "
                              "Escalate if score > 0.7." if decay_reports else "No decay detected.") + "\n\n"
        "ARCHAEOLOGIST NOTES:\n" + arch_section
    )
    try:
        ceo_decision = ceo_agent.run("\n".join(lib_summary_lines), agent_reports, stale_summary)
        for did in ceo_decision.get("kill_queue", []):
            log_decision("ceo", did, "kill_queue")
        for did in ceo_decision.get("build_queue", []):
            log_decision("ceo", did, "build_queue")
        for did in ceo_decision.get("investigate_queue", []):
            log_decision("ceo", did, "investigate_queue")
        ceo_decision["stale_queue"] = stale_ids  # deterministic override: CEO cannot hallucinate stale IDs
        for did in stale_ids:
            log_decision("ceo", did, "stale_queue")
        print("    → CEO synthesis complete", flush=True)
    except Exception as e:
        ceo_decision = {
            "agenda": [], "build_queue": [], "kill_queue": [],
            "investigate_queue": [], "stale_queue": [],
            "ceo_commentary": f"CEO synthesis failed: {e}",
        }
        print(f"    → CEO ERROR: {e}", flush=True)

    # Render markdown
    L = []
    L.append("# DARWIN DAILY BOARD MEETING — AI EDITION")
    L.append(f"## {today}")
    L.append("")
    L.append("```")
    L.append(f"library: {len(lib)} live discoveries   graveyard: {len(grave)} killed")
    for s in ["BACKLOG", "CANDIDATE", "TESTING", "SUPPORTED", "VALIDATED", "SHADOW",
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

    if ceo_decision.get("stale_queue"):
        L.append("## STALE QUEUE (demote to BACKLOG)")
        L.append("")
        for did in ceo_decision["stale_queue"]:
            L.append(f"- `{did}` — no progress; demote to BACKLOG to free WIP slot")
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
