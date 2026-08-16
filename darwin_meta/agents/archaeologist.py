"""DARWIN Meta-Engine — Archaeologist Agent (Role #3)

Connects discoveries to each other and to the graveyard.
Finds patterns across the lab's history: which hypotheses keep dying
for the same reason, which labs produce the most survivors, and
whether a new discovery is actually a re-hash of an old one.
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

from darwin_meta.agents.base_agent import BaseAgent


class ArchaeologistAgent(BaseAgent):
    """Mines the lab's history for patterns and connections."""

    ROLE_NAME = "archaeologist"
    SYSTEM_PROMPT = (
        "You are the Archaeologist at DARWIN Labs. You study the lab's entire history "
        "— live discoveries, the graveyard, agent performance logs — to find patterns.\n\n"
        "Your jobs:\n"
        "1. Link new discoveries to related past work (lineage).\n"
        "2. Identify recurring failure modes in the graveyard.\n"
        "3. Rank labs by survival rate.\n"
        "4. Detect 'zombie' hypotheses — ideas that keep coming back with new names.\n"
        "5. Surface institutional knowledge that other agents miss."
    )

    def run(self, library: list[dict], graveyard: list[dict],
            meta_logs: list[dict] | None = None) -> dict:
        """Analyse the full lab history and produce insights."""
        ctx = self._build_context(library, graveyard, meta_logs)
        prompt = (
            "Analyse the following lab history and produce structured insights.\n\n"
            + ctx
            + "\n\nReturn ONLY a JSON object with:\n"
            "- lineage_links: array of {from_id, to_id, reason}\n"
            "- recurring_failures: array of {pattern, count, affected_ids}\n"
            "- lab_survival_rates: object of {lab_name: survival_rate_0_to_1}\n"
            "- zombie_hypotheses: array of {title_pattern, occurrences}\n"
            "- institutional_notes: array of strings (advice for other agents)"
        )
        schema = {
            "type": "object",
            "properties": {
                "lineage_links": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "from_id": {"type": "string"},
                            "to_id": {"type": "string"},
                            "reason": {"type": "string"},
                        },
                        "required": ["from_id", "to_id", "reason"],
                    },
                },
                "recurring_failures": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "pattern": {"type": "string"},
                            "count": {"type": "integer"},
                            "affected_ids": {"type": "array", "items": {"type": "string"}},
                        },
                        "required": ["pattern", "count", "affected_ids"],
                    },
                },
                "lab_survival_rates": {"type": "object"},
                "zombie_hypotheses": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "title_pattern": {"type": "string"},
                            "occurrences": {"type": "integer"},
                        },
                        "required": ["title_pattern", "occurrences"],
                    },
                },
                "institutional_notes": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["lineage_links", "recurring_failures", "lab_survival_rates",
                         "zombie_hypotheses", "institutional_notes"],
        }
        return self._call(prompt, temperature=0.3, structured=True, schema=schema)

    def _build_context(self, library: list[dict], graveyard: list[dict],
                       meta_logs: list[dict] | None) -> str:
        lines = ["=== LIVE DISCOVERIES ==="]
        # Limit to most recent/important to fit 4096 ctx window
        for d in library[-20:]:
            lines.append(f"{d['id']} | {d['lab']} | {d['status']} | {d['title'][:80]}")
            hyp = d.get('hypothesis', '')[:60]
            lines.append(f"  Hyp: {hyp}")

        lines.append("\n=== GRAVEYARD (last 10) ===")
        for d in graveyard[-10:]:
            lines.append(f"{d['id']} | {d['lab']} | {d['title'][:80]}")
            kill = d.get('kill_cause', 'unknown')[:80]
            lines.append(f"  Killed: {kill}")

        # Compute basic stats locally too
        total = len(library) + len(graveyard)
        if total > 0:
            lines.append(f"\n=== BASIC STATS ===")
            lines.append(f"Total discoveries: {total}")
            lines.append(f"Survival rate: {len(library)}/{total} = {len(library)/total:.1%}")

            lab_counts = Counter(d["lab"] for d in library + graveyard)
            lab_kills = Counter(d["lab"] for d in graveyard)
            for lab, count in lab_counts.most_common():
                kills = lab_kills.get(lab, 0)
                surv = (count - kills) / count if count > 0 else 0
                lines.append(f"  {lab}: {count} total, {kills} killed, {surv:.0%} survival")

        if meta_logs:
            lines.append(f"\n=== AGENT PERFORMANCE (last {len(meta_logs)} runs) ===")
            agent_errors = defaultdict(int)
            for log in meta_logs[-50:]:
                if not log.get("success", True):
                    agent_errors[log.get("agent", "unknown")] += 1
            for agent, count in agent_errors.most_common():
                lines.append(f"  {agent}: {count} failures")

        return "\n".join(lines)


# Convenience function for CLI / daily run usage
def run_archaeologist(library_path: Path, graveyard_path: Path,
                      meta_log_path: Path | None, llm=None) -> dict:
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
    agent = ArchaeologistAgent(llm)
    return agent.run(lib, grave, logs)
