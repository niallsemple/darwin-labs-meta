"""DARWIN Meta-Engine — LLM Bridge

Robust interface to the local Kimi-Linear server with retry logic,
token budgeting, and structured-output parsing.

CRITICAL for CPU inference: a global threading.Lock serialises all
requests so the single-threaded llama-server is never overloaded.
"""

from __future__ import annotations

import json
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Optional

DEFAULT_BASE_URL = "http://127.0.0.1:8080/v1"
DEFAULT_MODEL = "kimi-linear-48b"

# Global lock: llama-server in CPU mode processes ONE request at a time.
# All LLMBridge instances share this lock so agents never collide.
_REQUEST_LOCK = threading.Lock()


@dataclass
class LLMResponse:
    content: str
    tokens_used: int = 0
    latency_ms: float = 0.0
    retries: int = 0


class LLMBridge:
    """Talk to the local llama-server (or any OpenAI-compatible endpoint)."""

    def __init__(self, base_url: str = DEFAULT_BASE_URL, model: str = DEFAULT_MODEL,
                 timeout: int = 180, max_retries: int = 5):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout
        self.max_retries = max_retries

    def chat(self, messages: list[dict], temperature: float = 0.3,
             max_tokens: int = 2048, **kwargs) -> LLMResponse:
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            **kwargs,
        }
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        last_err = None
        for attempt in range(self.max_retries):
            t0 = time.perf_counter()
            try:
                # Serialize all requests for CPU inference
                with _REQUEST_LOCK:
                    with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                        result = json.loads(resp.read().decode("utf-8"))
                content = result["choices"][0]["message"]["content"]
                usage = result.get("usage", {})
                latency = (time.perf_counter() - t0) * 1000
                return LLMResponse(
                    content=content,
                    tokens_used=usage.get("total_tokens", 0),
                    latency_ms=latency,
                    retries=attempt,
                )
            except urllib.error.HTTPError as e:
                last_err = e
                # 503 = server busy (CPU model still processing previous request)
                if e.code == 503:
                    backoff = min(5 * (2 ** attempt), 60)  # 5, 10, 20, 40, 60s
                else:
                    backoff = min(2 ** attempt, 30)
                if attempt < self.max_retries - 1:
                    time.sleep(backoff)
            except Exception as e:
                last_err = e
                if attempt < self.max_retries - 1:
                    time.sleep(min(2 ** attempt, 30))
        raise RuntimeError(f"LLM request failed after {self.max_retries} retries: {last_err}")

    def structured(self, messages: list[dict], schema: dict,
                   temperature: float = 0.1, max_tokens: int = 2048) -> dict:
        """Ask the model to return JSON matching a schema."""
        system_msg = (
            "You are a structured-output assistant. "
            "Respond ONLY with valid JSON matching the requested schema. "
            "No markdown, no commentary, no ```json fences."
        )
        msgs = [{"role": "system", "content": system_msg}] + messages
        resp = self.chat(msgs, temperature=temperature, max_tokens=max_tokens)
        text = resp.content.strip()
        # Strip fences if the model ignored instructions
        if text.startswith("```"):
            text = "\n".join(text.split("\n")[1:])
            if text.endswith("```"):
                text = text[:-3].strip()
            elif text.startswith("json"):
                text = text[4:].strip()
        return json.loads(text)

    def health(self) -> bool:
        """Check if the server is responding. Try /v1/models first."""
        try:
            with urllib.request.urlopen(
                f"{self.base_url}/models", timeout=5
            ) as resp:
                return resp.status == 200
        except Exception:
            pass
        # Fallback: try the legacy health endpoint
        try:
            with urllib.request.urlopen(
                f"{self.base_url.replace('/v1','')}/health", timeout=5
            ) as resp:
                return resp.status == 200
        except Exception:
            return False
