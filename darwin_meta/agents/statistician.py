"""DARWIN Meta-Engine — Statistician Agent (Role #5)

Takes a discovery and its data, runs significance tests, checks for
overfitting, multiple-testing bias, and sample-size sufficiency.
"""

from __future__ import annotations

from darwin_meta.agents.base_agent import BaseAgent


class StatisticianAgent(BaseAgent):
    """Evaluates statistical rigour of a discovery."""

    ROLE_NAME = "statistician"
    SYSTEM_PROMPT = (
        "You are the Statistician at DARWIN Labs. Your ONLY job is to kill hypotheses "
        "by critiquing VERIFIED numbers. You are handed experiment results produced by "
        "deterministic code (never by you). You are suspicious of EVERYTHING: small "
        "samples, p-hacking, selection bias, regime overfitting, look-ahead leakage, "
        "multiple testing across the whole hypothesis stream.\n\n"
        "You NEVER calculate statistics yourself. If no experiment results are provided, "
        "say so and treat every self-reported metric as unverified.\n\n"
        "Your output must include:\n"
        "- verdict: 'pass' | 'fail' | 'watch' | 'pending'\n"
        "- effect_size and unit (quoted from the verified data, or null)\n"
        "- n (sample size, quoted from the verified data, or null)\n"
        "- t_stat and p_value (quoted, or null)\n"
        "- sharpe_ratio if applicable\n"
        "- max_drawdown if applicable\n"
        "- concerns: list of specific threats to validity\n"
        "- recommendation: what would strengthen or kill this"
    )

    def run(self, discovery_context: str, data_summary: str) -> dict:
        prompt = (
            "Evaluate the following discovery with statistical rigour.\n\n"
            "DISCOVERY CONTEXT:\n" + discovery_context + "\n\n"
            "DATA SUMMARY:\n" + data_summary + "\n\n"
            "Return ONLY a JSON object with these exact keys:\n"
            "- verdict (string: pass/fail/watch/pending)\n"
            "- effect_size (number or null)\n"
            "- effect_unit (string)\n"
            "- n (integer or null)\n"
            "- t_stat (number or null)\n"
            "- p_value (number or null)\n"
            "- sharpe_ratio (number or null)\n"
            "- max_drawdown (number or null)\n"
            "- concerns (array of strings)\n"
            "- recommendation (string)"
        )
        schema = {
            "type": "object",
            "properties": {
                "verdict": {"type": "string", "enum": ["pass", "fail", "watch", "pending"]},
                "effect_size": {"type": ["number", "null"]},
                "effect_unit": {"type": "string"},
                "n": {"type": ["integer", "null"]},
                "t_stat": {"type": ["number", "null"]},
                "p_value": {"type": ["number", "null"]},
                "sharpe_ratio": {"type": ["number", "null"]},
                "max_drawdown": {"type": ["number", "null"]},
                "concerns": {"type": "array", "items": {"type": "string"}},
                "recommendation": {"type": "string"},
            },
            "required": ["verdict", "concerns", "recommendation"],
        }
        return self._call(prompt, temperature=0.2, structured=True, schema=schema)
