"""DARWIN Meta-Engine — CEO Agent (Role #1)

Chairs the board meeting.  Synthesises all agent outputs into a
daily BUILD / INVESTIGATE / KILL agenda.
"""

from __future__ import annotations

from darwin_meta.agents.base_agent import BaseAgent


class CEOAgent(BaseAgent):
    """Generates the daily strategic agenda."""

    ROLE_NAME = "ceo"
    SYSTEM_PROMPT = (
        "You are the CEO of DARWIN Labs. Your job is to synthesise the work of "
        "nine research roles into a single daily agenda. You are decisive.\n\n"
        "You must produce:\n"
        "- agenda: array of actions (each: action, target_id, rationale)\n"
        "- build_queue: discoveries to advance\n"
        "- kill_queue: discoveries to reject\n"
        "- investigate_queue: discoveries needing more data\n"
        "- resource_allocation: which labs get compute attention today\n"
        "- ceo_commentary: one paragraph on the state of the lab"
    )

    def run(self, library_summary: str, agent_reports: str) -> dict:
        prompt = (
            "You are chairing the DARWIN Daily Board Meeting.\n\n"
            "LIBRARY STATE:\n" + library_summary + "\n\n"
            "AGENT REPORTS:\n" + agent_reports + "\n\n"
            "Produce a JSON object with:\n"
            "- agenda: array of {action, target_id, rationale}\n"
            "- build_queue: array of discovery IDs to advance\n"
            "- kill_queue: array of discovery IDs to reject\n"
            "- investigate_queue: array of discovery IDs needing more work\n"
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
                "resource_allocation": {"type": "object"},
                "ceo_commentary": {"type": "string"},
            },
            "required": ["agenda", "build_queue", "kill_queue", "investigate_queue", "ceo_commentary"],
        }
        return self._call(prompt, temperature=0.3, structured=True, schema=schema)
