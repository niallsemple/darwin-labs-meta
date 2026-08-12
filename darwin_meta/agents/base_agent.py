"""DARWIN Meta-Engine — Base Agent

Every research-company role inherits from this.  Provides:
- prompt templating with system + task + context
- structured vs free-form output modes
- performance logging (for the meta-loop)
- cost/time tracking
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from darwin_meta.utils.llm_bridge import LLMBridge, LLMResponse

META_LOG_PATH = Path(__file__).resolve().parent.parent / "loops" / "agent_performance.jsonl"


@dataclass
class AgentRun:
    agent_name: str
    task_type: str
    prompt_tokens_estimate: int = 0
    response: Optional[LLMResponse] = None
    output_summary: str = ""
    success: bool = True
    timestamp: str = ""
    latency_ms: float = 0.0

    def to_dict(self) -> dict:
        return {
            "agent": self.agent_name,
            "task": self.task_type,
            "timestamp": self.timestamp or time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "latency_ms": round(self.latency_ms, 1),
            "tokens_used": self.response.tokens_used if self.response else 0,
            "success": self.success,
            "output_summary": self.output_summary[:200],
        }


class BaseAgent:
    """Abstract base for all nine research-company roles."""

    ROLE_NAME = "base"
    SYSTEM_PROMPT = "You are a member of DARWIN Labs, an autonomous discovery laboratory."

    def __init__(self, llm: Optional[LLMBridge] = None):
        self.llm = llm or LLMBridge()
        self._meta_log_path = META_LOG_PATH
        self._meta_log_path.parent.mkdir(parents=True, exist_ok=True)

    def _call(self, user_prompt: str, temperature: float = 0.3,
              max_tokens: int = 2048, structured: bool = False,
              schema: Optional[dict] = None) -> str | dict:
        """Internal LLM call with performance logging."""
        t0 = time.perf_counter()
        messages = [
            {"role": "system", "content": self.SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ]
        try:
            if structured and schema:
                result = self.llm.structured(messages, schema, temperature, max_tokens)
            else:
                result = self.llm.chat(messages, temperature, max_tokens).content
            latency = (time.perf_counter() - t0) * 1000
            self._log_run(AgentRun(
                agent_name=self.ROLE_NAME,
                task_type="inference",
                latency_ms=latency,
                output_summary=str(result)[:200],
                success=True,
            ))
            return result
        except Exception as e:
            self._log_run(AgentRun(
                agent_name=self.ROLE_NAME,
                task_type="inference",
                success=False,
                output_summary=str(e)[:200],
            ))
            raise

    def _log_run(self, run: AgentRun) -> None:
        with open(self._meta_log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(run.to_dict(), ensure_ascii=False) + "\n")

    def run(self, *args, **kwargs):
        raise NotImplementedError("Subclass must implement run()")
