"""DARWIN Meta-Engine — Outcome Attribution

The piece that turns meta-learning from prompt-rotation into learning which
research paths produce alpha.

Connects every logged agent decision (decisions.jsonl) to the CURRENT fate
of the discovery it concerned (library + graveyard), and scores the agent:

- explorer:     validated-discoveries-per-hypothesis. A proposal that gets
                KILLED scores 0; one that reaches VALIDATED+ scores 1.
- statistician: penalised for FALSE PASSES (said pass, discovery died) and
                FALSE KILLS (said fail, discovery went on to validate).
- sceptic:      rewarded for USEFUL KILLS (attacked, discovery died) and
                penalised for crying wolf on discoveries that validated.
- ceo:          research-resource efficiency — kill_queue entries that died
                are good; build/investigate entries that advanced are good;
                the reverse are wasted budget.

Unresolved fates (discovery still CANDIDATE/TESTING) score neutral 0.5 —
recent decisions shouldn't tank an agent before reality has spoken.

Includes a one-time backfill from historical board-meeting reports so the
scorer has data before the structured log accumulates.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path

from darwin_meta.loops.decision_log import load_decisions
from darwin_meta.loops.meta_learning import AgentScore
from laboratory import library_store as store

ROOT = Path(__file__).resolve().parent.parent.parent
REPORTS = ROOT / "reports"

# fate ladder: where a discovery ended up, as a 0..1 outcome
FATE_SCORE = {
    "KILLED": 0.0,
    "CANDIDATE": 0.3,
    "TESTING": 0.45,
    "SUPPORTED": 0.65,
    "VALIDATED": 0.8,
    "SHADOW": 0.9,
    "MICRO_LIVE": 0.95,
    "PROMOTED": 1.0,
}
UNRESOLVED = {"CANDIDATE", "TESTING"}


def _fates() -> dict[str, str]:
    """discovery_id -> current status, library and graveyard combined."""
    out = {}
    for d in store.load_graveyard():
        out[d.id] = "KILLED"
    for d in store.load_library():
        out[d.id] = d.status
    return out


def score_decision(agent: str, decision: str, fate: str, detail: dict) -> tuple[float, str]:
    """One decision, one fate -> (score 0..1, reason). Neutral 0.5 when the
    discovery hasn't resolved yet."""
    alive_advanced = fate in ("SUPPORTED", "VALIDATED", "SHADOW", "MICRO_LIVE", "PROMOTED")

    if fate in UNRESOLVED:
        return 0.5, f"unresolved ({fate})"

    if agent == "explorer":
        return FATE_SCORE[fate], f"proposal fate: {fate}"

    if agent == "statistician":
        if decision == "pass":
            return (0.0, "FALSE PASS — died after pass") if fate == "KILLED" \
                else (1.0, f"pass upheld ({fate})")
        if decision == "fail":
            return (1.0, "correct kill") if fate == "KILLED" \
                else (0.0, f"FALSE KILL — later {fate}")
        return 0.6 if alive_advanced else 0.4, f"watch/pending, fate {fate}"

    if agent == "sceptic":
        kill_prob = detail.get("kill_probability", 0.5)
        attacked = decision == "fail" or kill_prob >= 0.5
        if attacked:
            return (1.0, "useful kill") if fate == "KILLED" \
                else (0.0, f"cried wolf — later {fate}")
        return (0.0, f"missed — cleared a discovery that died") if fate == "KILLED" \
            else (1.0, f"correctly cleared ({fate})")

    if agent == "ceo":
        if decision == "kill_queue":
            return (1.0, "kill confirmed") if fate == "KILLED" \
                else (0.2, f"kill-queued but later {fate}")
        if decision in ("build_queue", "investigate_queue"):
            return (1.0, f"investment paid off ({fate})") if alive_advanced \
                else (0.2, f"wasted budget — later {fate}")
        return 0.5, f"agenda note, fate {fate}"

    return FATE_SCORE.get(fate, 0.5), f"generic fate {fate}"


def backfill_from_reports(reports_dir: Path = REPORTS) -> list[dict]:
    """Parse historical board-ai-*.md reports into decision records so the
    scorer has history before decisions.jsonl accumulates. Statistician lines
    look like 'D-0004: pass — ...', sceptic lines like
    'D-0004: fail (kill_prob=0.70) — ...', CEO queues are bulleted ids."""
    out = []
    if not reports_dir.is_dir():
        return out
    for path in sorted(reports_dir.glob("board-ai-*.md")):
        day = path.stem.replace("board-ai-", "")
        section = None
        for line in path.read_text().splitlines():
            h = re.match(r"^##\s+(.+)", line)
            if h:
                section = h.group(1).upper()
                continue
            m = re.match(r"^- (D-\d+): (pass|fail|watch|pending)", line)
            if m and section and "STATISTICIAN" in section:
                out.append({"ts": day, "agent": "statistician",
                            "discovery_id": m.group(1), "decision": m.group(2),
                            "detail": {"backfilled": True}})
                continue
            m = re.match(r"^- (D-\d+): (pass|fail|watch|pending) \(kill_prob=([\d.]+)\)", line)
            if m and section and "SCEPTIC" in section:
                out.append({"ts": day, "agent": "sceptic",
                            "discovery_id": m.group(1), "decision": m.group(2),
                            "detail": {"kill_probability": float(m.group(3)),
                                       "backfilled": True}})
                continue
            m = re.match(r"^- `?(D-\d+)`?$", line.strip())
            if m and section:
                for q, dec in (("KILL QUEUE", "kill_queue"),
                               ("BUILD QUEUE", "build_queue"),
                               ("INVESTIGATE QUEUE", "investigate_queue")):
                    if q in section:
                        out.append({"ts": day, "agent": "ceo",
                                    "discovery_id": m.group(1), "decision": dec,
                                    "detail": {"backfilled": True}})
                        break
    return out


def attribute_outcomes(include_backfill: bool = True) -> dict:
    """Score every decision against current fates. Returns a summary plus
    AgentScore objects ready for MetaLearningLoop.ingest_outcomes()."""
    decisions = load_decisions()
    seen = {(d["ts"], d["agent"], d["discovery_id"], d["decision"]) for d in decisions}
    if include_backfill:
        for b in backfill_from_reports():
            key = (b["ts"], b["agent"], b["discovery_id"], b["decision"])
            if key not in seen:
                decisions.append(b)

    # also: every anomaly-engine evidence note is an explorer proposal
    for d in store.load_library() + store.load_graveyard():
        for e in d.evidence:
            if e.author == "anomaly_engine":
                decisions.append({"ts": e.date, "agent": "explorer",
                                  "discovery_id": d.id, "decision": "propose",
                                  "detail": {"from_evidence": True}})

    fates = _fates()
    per_agent: dict[str, list[dict]] = {}
    for dec in decisions:
        did = dec["discovery_id"]
        if did not in fates:
            continue  # decision references an unknown id — skip
        score, reason = score_decision(dec["agent"], dec["decision"], fates[did],
                                       dec.get("detail", {}))
        per_agent.setdefault(dec["agent"], []).append({
            "discovery_id": did, "decision": dec["decision"],
            "fate": fates[did], "score": score, "reason": reason, "ts": dec["ts"],
        })

    scores, agents_summary = [], {}
    for agent, rows in per_agent.items():
        avg = round(sum(r["score"] for r in rows) / len(rows), 3)
        agents_summary[agent] = {"decisions": len(rows), "avg_score": avg, "rows": rows}
        notes = "; ".join(f"{r['discovery_id']}:{r['decision']}→{r['fate']}"
                          for r in rows[-5:])
        scores.append(AgentScore(agent_name=agent, task_type="outcome",
                                 outcome=avg, notes=notes))

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "agents": agents_summary,
        "scores": scores,
        "n_decisions": len(decisions),
    }


def render_outcome_md(result: dict) -> str:
    L = ["## Outcome-Attributed Agent Scores", "",
         "Every score below is derived from what ACTUALLY happened to the "
         "discovery the agent touched — not from self-assessment.", ""]
    if not result["agents"]:
        L.append("No attributable decisions yet.")
        return "\n".join(L) + "\n"
    L.append("| Agent | Decisions | Outcome Score | Reading |")
    L.append("|-------|-----------|---------------|---------|")
    reading = {"explorer": "validated-per-hypothesis",
               "statistician": "1 − false-pass/false-kill rate",
               "sceptic": "useful-kill rate",
               "ceo": "research-resource efficiency"}
    for agent, s in sorted(result["agents"].items()):
        L.append(f"| {agent} | {s['decisions']} | {s['avg_score']:.2f} | "
                 f"{reading.get(agent, 'outcome-linked')} |")
    for agent, s in sorted(result["agents"].items()):
        L += ["", f"### {agent} — recent decisions", ""]
        for r in s["rows"][-5:]:
            L.append(f"- `{r['discovery_id']}` {r['decision']} → **{r['fate']}** "
                     f"(score {r['score']}) — {r['reason']}")
    return "\n".join(L) + "\n"


if __name__ == "__main__":
    res = attribute_outcomes()
    print(render_outcome_md(res))
