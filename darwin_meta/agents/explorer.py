"""DARWIN Meta-Engine — Explorer Agent (Role #2)

Searches for patterns in raw data, frames them as falsifiable hypotheses,
and produces Discovery-shaped candidates.
"""

from __future__ import annotations

from darwin_meta.agents.base_agent import BaseAgent


class ExplorerAgent(BaseAgent):
    """Generates candidate discoveries from data patterns."""

    ROLE_NAME = "explorer"
    SYSTEM_PROMPT = (
        "You are the Explorer at DARWIN Labs. Your job is to find strange patterns "
        "in data and frame them as falsifiable hypotheses. You NEVER claim something "
        "is true — you only flag it as worth testing. Every hypothesis must include:\n"
        "1. A clear, testable prediction.\n"
        "2. Kill criteria (what would prove it false).\n"
        "3. The data source and window.\n"
        "You are rewarded for quantity AND quality of candidates, but punished for "
        "non-falsifiable hand-waving."
    )

    def run(self, data_context: str, max_candidates: int = 3) -> list[dict]:
        prompt = (
            f"Given the following data context, generate up to {max_candidates} "
            "candidate discoveries. Each must be a JSON object with:\n"
            "- title: short descriptive name\n"
            "- hypothesis: one-sentence falsifiable claim\n"
            "- falsifiable_prediction: exact metric and direction expected\n"
            "- kill_criteria: what observation would falsify it\n"
            "- data_source: where this was observed\n"
            "- regime_notes: where it might / might not work\n\n"
            "DATA CONTEXT:\n" + data_context + "\n\n"
            "Return ONLY a JSON array of objects. No commentary."
        )
        schema = {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "hypothesis": {"type": "string"},
                    "falsifiable_prediction": {"type": "string"},
                    "kill_criteria": {"type": "string"},
                    "data_source": {"type": "string"},
                    "regime_notes": {"type": "string"},
                },
                "required": ["title", "hypothesis", "falsifiable_prediction", "kill_criteria"],
            },
        }
        result = self._call(prompt, temperature=0.4, structured=True, schema=schema)
        return result if isinstance(result, list) else []
