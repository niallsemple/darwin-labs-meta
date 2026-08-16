"""DARWIN Meta-Engine — Sceptic Agent (Role #4)

Attacks every discovery.  Looks for leakage, liquidity artifacts,
regime flukes, survivorship bias, and hidden assumptions.
"""

from __future__ import annotations

from darwin_meta.agents.base_agent import BaseAgent


class ScepticAgent(BaseAgent):
    """Generates aggressive attacks on a discovery."""

    ROLE_NAME = "sceptic"
    SYSTEM_PROMPT = (
        "You are the Sceptic at DARWIN Labs. You are PAID to kill discoveries. "
        "You are cynical, thorough, and relentless. Your default assumption is that "
        "every pattern is a fluke until proven otherwise.\n\n"
        "Your output must include:\n"
        "- verdict: 'pass' | 'fail' | 'watch' | 'pending'\n"
        "- attacks: list of specific attacks (each with severity: critical/major/minor)\n"
        "- hidden_assumptions: what is the discoverer assuming without saying?\n"
        "- alternative_explanations: what else could explain this pattern?\n"
        "- kill_probability: 0-1 estimate that this will die in forward testing\n"
        "- recommendation: proceed / hold / kill"
    )

    def run(self, discovery_context: str, evidence_summary: str) -> dict:
        prompt = (
            "Tear apart the following discovery. Find every flaw, hidden assumption, "
            "and alternative explanation. Be ruthless.\n\n"
            "DISCOVERY CONTEXT:\n" + discovery_context + "\n\n"
            "EVIDENCE SUMMARY:\n" + evidence_summary + "\n\n"
            "Return ONLY a JSON object with these exact keys:\n"
            "- verdict (string: pass/fail/watch/pending)\n"
            "- attacks (array of objects: {attack, severity})\n"
            "- hidden_assumptions (array of strings)\n"
            "- alternative_explanations (array of strings)\n"
            "- kill_probability (number 0-1)\n"
            "- recommendation (string)"
        )
        schema = {
            "type": "object",
            "properties": {
                "verdict": {"type": "string", "enum": ["pass", "fail", "watch", "pending"]},
                "attacks": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "attack": {"type": "string"},
                            "severity": {"type": "string", "enum": ["critical", "major", "minor"]},
                        },
                        "required": ["attack", "severity"],
                    },
                },
                "hidden_assumptions": {"type": "array", "items": {"type": "string"}},
                "alternative_explanations": {"type": "array", "items": {"type": "string"}},
                "kill_probability": {"type": "number"},
                "recommendation": {"type": "string"},
            },
            "required": ["verdict", "attacks", "kill_probability", "recommendation"],
        }
        return self._call(prompt, temperature=0.5, structured=True, schema=schema, max_tokens=512)
