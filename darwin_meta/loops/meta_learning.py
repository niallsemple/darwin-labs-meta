"""DARWIN Meta-Engine — Meta-Learning Loop (v2)

Tracks agent performance over time. Learns which prompts, temperatures,
and strategies produce better outcomes. Actually ADAPTS agent prompts.

New in v2:
- Prompt registry: tracks which prompts work best per agent
- Auto-suggested prompt improvements when avg_outcome < 0.5
- Agents query this loop for their optimal config before running
"""

from __future__ import annotations

import json
import statistics
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

META_LOG_PATH = Path(__file__).resolve().parent / "agent_performance.jsonl"
META_STATE_PATH = Path(__file__).resolve().parent / "meta_state.json"

# Built-in prompt variants for underperforming agents
PROMPT_VARIANTS = {
    "statistician": [
        "You are the Statistician at DARWIN Labs. Your ONLY job is to kill hypotheses with numbers. You are suspicious of EVERYTHING: small samples, p-hacking, selection bias, regime overfitting, look-ahead leakage.",
        "You are a ruthless statistical reviewer. Every claim must die by the numbers. Demand effect sizes, confidence intervals, and pre-registration. No p-hacking survives your review.",
        "You are a Bayesian skeptic. Convert every frequentist claim into a posterior probability. If the prior doesn't support the claim, reject it. Demand replication evidence.",
    ],
    "sceptic": [
        "You are the Sceptic at DARWIN Labs. You are PAID to kill discoveries. You are cynical, thorough, and relentless. Your default assumption is that every pattern is a fluke until proven otherwise.",
        "You are a professional debunker. Every discovery is guilty until proven innocent. Find the hidden assumptions, the survivorship bias, the regime dependency. Show no mercy.",
        "You are a forensic accountant for trading strategies. Trace every dollar of profit to its source. If you can't explain it, kill it.",
    ],
    "ceo": [
        "You are the CEO of DARWIN Labs. Your job is to synthesise the work of nine research roles into a single daily agenda. You are decisive and data-driven.",
        "You are a portfolio manager reviewing research proposals. Only the strongest evidence gets capital. Be ruthless about resource allocation.",
        "You are the editor-in-chief of a top-tier journal. Most submissions get rejected. Only paradigm-shifting work advances.",
    ],
    "archaeologist": [
        "You are the Archaeologist at DARWIN Labs. You study the lab's entire history to find patterns. Link discoveries, identify recurring failures, rank labs by survival rate.",
        "You are a historian of science tracing intellectual lineages. Every new idea has ancestors. Find them and learn from their fates.",
    ],
}

DEFAULT_PROMPTS = {k: v[0] for k, v in PROMPT_VARIANTS.items()}


@dataclass
class AgentScore:
    agent_name: str
    task_type: str
    outcome: float  # 0 = terrible, 1 = perfect
    notes: str = ""


class MetaLearningLoop:
    """Reviews agent logs and produces improvement recommendations.
    Actually adapts prompts, not just temperature."""

    def __init__(self, log_path: Path = META_LOG_PATH,
                 state_path: Path = META_STATE_PATH):
        self.log_path = log_path
        self.state_path = state_path
        self._state = self._load_state()

    def _load_state(self) -> dict:
        if self.state_path.exists():
            return json.loads(self.state_path.read_text())
        return {
            "agent_configs": {},
            "revision": 0,
            "created": datetime.now(timezone.utc).isoformat(),
            "prompt_registry": {},  # agent_name -> {variant_idx, scores}
        }

    def _save_state(self) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.state_path.write_text(json.dumps(self._state, indent=2, ensure_ascii=False) + "\n")

    def ingest_outcomes(self, scores: list[AgentScore]) -> None:
        """Feed back outcome scores for recent agent runs."""
        for s in scores:
            key = f"{s.agent_name}:{s.task_type}"
            if key not in self._state["agent_configs"]:
                self._state["agent_configs"][key] = {
                    "outcomes": [],
                    "avg_outcome": 0.0,
                    "recommended_temp": 0.3,
                    "recommended_max_tokens": 2048,
                    "prompt_variant": 0,
                    "prompt_scores": {},  # variant_idx -> list of outcomes
                }
            cfg = self._state["agent_configs"][key]
            cfg["outcomes"].append({
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "outcome": s.outcome,
                "notes": s.notes,
            })
            # Keep last 50
            cfg["outcomes"] = cfg["outcomes"][-50:]
            cfg["avg_outcome"] = round(
                statistics.mean(o["outcome"] for o in cfg["outcomes"]), 3
            )

            # Temperature heuristic
            if cfg["avg_outcome"] < 0.4:
                cfg["recommended_temp"] = 0.1
            elif cfg["avg_outcome"] < 0.7:
                cfg["recommended_temp"] = 0.3
            else:
                cfg["recommended_temp"] = 0.5

            # Prompt evolution: if underperforming, try next variant
            if cfg["avg_outcome"] < 0.5 and s.agent_name in PROMPT_VARIANTS:
                current_variant = cfg.get("prompt_variant", 0)
                n_variants = len(PROMPT_VARIANTS[s.agent_name])
                if n_variants > 1:
                    # Record score for current variant
                    if current_variant not in cfg["prompt_scores"]:
                        cfg["prompt_scores"][current_variant] = []
                    cfg["prompt_scores"][current_variant].append(s.outcome)
                    cfg["prompt_scores"][current_variant] = cfg["prompt_scores"][current_variant][-20:]

                    # If current variant has 5+ scores and avg < 0.5, rotate
                    scores_for_variant = cfg["prompt_scores"][current_variant]
                    if len(scores_for_variant) >= 5:
                        avg_for_variant = statistics.mean(scores_for_variant)
                        if avg_for_variant < 0.5:
                            new_variant = (current_variant + 1) % n_variants
                            cfg["prompt_variant"] = new_variant
                            print(f"[Meta-Learning] {s.agent_name}: rotating prompt variant {current_variant} -> {new_variant} "
                                  f"(avg={avg_for_variant:.2f})")

        self._state["revision"] += 1
        self._save_state()

    def get_prompt(self, agent_name: str) -> str:
        """Get the currently recommended system prompt for an agent."""
        key = f"{agent_name}:inference"
        cfg = self._state["agent_configs"].get(key, {})
        variant = cfg.get("prompt_variant", 0)
        variants = PROMPT_VARIANTS.get(agent_name, [DEFAULT_PROMPTS.get(agent_name, "")])
        return variants[variant % len(variants)]

    def recommend(self, agent_name: str, task_type: str) -> dict:
        """Get recommended settings for an agent/task combo."""
        key = f"{agent_name}:{task_type}"
        cfg = self._state["agent_configs"].get(key, {})
        return {
            "temperature": cfg.get("recommended_temp", 0.3),
            "max_tokens": cfg.get("recommended_max_tokens", 2048),
            "avg_outcome": cfg.get("avg_outcome", None),
            "n_observations": len(cfg.get("outcomes", [])),
            "prompt_variant": cfg.get("prompt_variant", 0),
        }

    def report(self) -> dict:
        """Generate a meta-learning summary report."""
        report = {
            "revision": self._state["revision"],
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "agents": {},
            "recommendations": [],
        }
        for key, cfg in self._state["agent_configs"].items():
            agent, task = key.split(":", 1)
            report["agents"][agent] = {
                "task": task,
                "avg_outcome": cfg["avg_outcome"],
                "observations": len(cfg["outcomes"]),
                "recommended_temp": cfg["recommended_temp"],
                "prompt_variant": cfg.get("prompt_variant", 0),
            }
            if cfg["avg_outcome"] < 0.5:
                variant = cfg.get("prompt_variant", 0)
                report["recommendations"].append(
                    f"{agent} ({task}) is underperforming (avg={cfg['avg_outcome']}). "
                    f"Now using prompt variant {variant}."
                )
        return report

    def render_report_md(self) -> str:
        r = self.report()
        lines = [
            "# DARWIN Meta-Learning Report",
            f"_Revision {r['revision']} — {r['generated_at'][:10]}_",
            "",
            "## Agent Performance",
            "",
            "| Agent | Task | Avg Outcome | Obs | Rec. Temp | Prompt Variant |",
            "|-------|------|-------------|-----|-----------|----------------|",
        ]
        for agent, data in r["agents"].items():
            lines.append(
                f"| {agent} | {data['task']} | {data['avg_outcome']:.2f} | "
                f"{data['observations']} | {data['recommended_temp']} | {data.get('prompt_variant', 0)} |"
            )
        if r["recommendations"]:
            lines += ["", "## Recommendations", ""]
            for rec in r["recommendations"]:
                lines.append(f"- {rec}")
        else:
            lines += ["", "## Recommendations", "", "All agents performing adequately."]
        return "\n".join(lines) + "\n"
