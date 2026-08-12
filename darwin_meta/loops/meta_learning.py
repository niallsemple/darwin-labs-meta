"""DARWIN Meta-Engine — Meta-Learning Loop

Tracks agent performance over time.  Learns which prompts, temperatures,
and strategies produce better outcomes.  Adjusts agent behaviour.

The loop is simple but powerful:\n
1. Log every agent run (already done in BaseAgent)\n2. Periodically score outcomes (human or automated feedback)\n3. Adjust prompts / temperature / strategy based on what worked\n4. Publish a meta-report
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


@dataclass
class AgentScore:
    agent_name: str
    task_type: str
    outcome: float  # 0 = terrible, 1 = perfect
    notes: str = ""


class MetaLearningLoop:
    """Reviews agent logs and produces improvement recommendations."""

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
            # Simple temperature heuristic: low outcome -> more conservative (lower temp)
            if cfg["avg_outcome"] < 0.4:
                cfg["recommended_temp"] = 0.1
            elif cfg["avg_outcome"] < 0.7:
                cfg["recommended_temp"] = 0.3
            else:
                cfg["recommended_temp"] = 0.5
        self._state["revision"] += 1
        self._save_state()

    def recommend(self, agent_name: str, task_type: str) -> dict:
        """Get recommended settings for an agent/task combo."""
        key = f"{agent_name}:{task_type}"
        cfg = self._state["agent_configs"].get(key, {})
        return {
            "temperature": cfg.get("recommended_temp", 0.3),
            "max_tokens": cfg.get("recommended_max_tokens", 2048),
            "avg_outcome": cfg.get("avg_outcome", None),
            "n_observations": len(cfg.get("outcomes", [])),
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
            }
            if cfg["avg_outcome"] < 0.5:
                report["recommendations"].append(
                    f"{agent} ({task}) is underperforming (avg={cfg['avg_outcome']}). "
                    f"Consider prompt rewrite or stricter output schema."
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
            "| Agent | Task | Avg Outcome | Obs | Rec. Temp |",
            "|-------|------|-------------|-----|-----------|",
        ]
        for agent, data in r["agents"].items():
            lines.append(
                f"| {agent} | {data['task']} | {data['avg_outcome']:.2f} | "
                f"{data['observations']} | {data['recommended_temp']} |"
            )
        if r["recommendations"]:
            lines += ["", "## Recommendations", ""]
            for rec in r["recommendations"]:
                lines.append(f"- {rec}")
        else:
            lines += ["", "## Recommendations", "", "All agents performing adequately."]
        return "\n".join(lines) + "\n"
