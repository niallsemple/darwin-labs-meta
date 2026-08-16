"""DARWIN Meta-Engine — CEO Agent (Role #1)

Chairs the board meeting.  Synthesises all agent outputs into a
daily BUILD / INVESTIGATE / KILL / DEMOTE agenda.
"""

from __future__ import annotations

from darwin_meta.agents.base_agent import BaseAgent


class CEOAgent(BaseAgent):
    """Generates the daily strategic agenda."""

    ROLE_NAME = "ceo"
    SYSTEM_PROMPT = (
        "You are the CEO of DARWIN Labs. Your job is to synthesise the work of "
        "nine research roles into a single daily agenda. You are decisive.\n\n"
        "Every day you MUST re-evaluate CANDIDATE discoveries for staleness. "
        "A CANDIDATE is stale if it has sat with no evidence progress, no "
        "actionable next step, or no falsification work for too long. "
        "Stale CANDIDATEs waste the WIP limit (max 10). Demote them to BACKLOG "
        "or kill them — do not let them sit indefinitely.\n\n"
        "You must produce:\n"
        "- agenda: array of actions (each: action, target_id, rationale)\n"
        "- build_queue: discoveries to advance\n"
        "- kill_queue: discoveries to reject\n"
        "- investigate_queue: discoveries needing more data\n"
        "- stale_queue: CANDIDATE discoveries to demote to BACKLOG (stalled, no progress)\n"
        "- resource_allocation: which labs get compute attention today\n"
        "- ceo_commentary: one paragraph on the state of the lab"
    )

    def run(self, library_summary: str, agent_reports: str, stale_summary: str = "") -> dict:
        stale_section = f"\nSTALE CANDIDATE REVIEW:\n{stale_summary}\n" if stale_summary else ""
        prompt = (
            "You are chairing the DARWIN Daily Board Meeting.\n\n"
            "LIBRARY STATE:\n" + library_summary + "\n\n"
            "AGENT REPORTS:\n" + agent_reports +
            stale_section + "\n"
            "Your daily mandate includes re-evaluating CANDIDATEs for staleness. "
            "If a CANDIDATE has no recent evidence, no defined next_action, or no "
            "falsification progress, demote it to BACKLOG via stale_queue. "
            "Do NOT let CANDIDATE slots sit idle.\n\n"
            "Produce a JSON object with:\n"
            "- agenda: array of {action, target_id, rationale}\n"
            "- build_queue: array of discovery IDs to advance\n"
            "- kill_queue: array of discovery IDs to reject\n"
            "- investigate_queue: array of discovery IDs needing more work\n"
            "- stale_queue: array of CANDIDATE discovery IDs to demote to BACKLOG\n"
            "- resource_allocation: {lab_name: priority_score 0-10}\n"
            "- ceo_commentary: string (one paragraph)"
        )
        schema = {
            "type": "object",
            "properties": {
                "agenda": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "action": {"type": "string"},
                            "target_id": {"type": "string"},
                            "rationale": {"type": "string"},
                        },
                        "required": ["action", "target_id", "rationale"],
                    },
                },
                "build_queue": {"type": "array", "items": {"type": "string"}},
                "kill_queue": {"type": "array", "items": {"type": "string"}},
                "investigate_queue": {"type": "array", "items": {"type": "string"}},
                "stale_queue": {"type": "array", "items": {"type": "string"}},
                "resource_allocation": {"type": "object"},
                "ceo_commentary": {"type": "string"},
            },
            "required": ["agenda", "build_queue", "kill_queue", "investigate_queue", "stale_queue", "ceo_commentary"],
        }
        return self._call(prompt, temperature=0.3, structured=True, schema=schema)
