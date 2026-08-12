"""DARWIN Self-Improve — Implementer

When the Gap Analyser approves a repo, this module generates a
concrete implementation plan and writes the code.

It is CONSERVATIVE: it only adds new modules, never overwrites
existing code without a backup. It also adds tests.
"""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from darwin_meta.utils.llm_bridge import LLMBridge

ROOT = Path(__file__).resolve().parent.parent.parent
IMPROVEMENT_LOG = ROOT / "reports" / "improvement_log.jsonl"


@dataclass
class ImplementationResult:
    success: bool
    files_created: list[str]
    files_modified: list[str]
    tests_added: list[str]
    error: str = ""


def _backup_file(path: Path) -> Path:
    """Create a .bak timestamped copy."""
    backup = path.with_suffix(path.suffix + f".bak_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}")
    shutil.copy2(path, backup)
    return backup


def generate_module_code(gap_report, llm: Optional[LLMBridge] = None) -> str:
    """Ask the local LLM to generate Python module code for the gap."""
    llm = llm or LLMBridge()

    messages = [
        {"role": "system", "content": (
            "You are a senior Python engineer at DARWIN Labs. You write clean, "
            "well-documented, production-ready code. You follow PEP 8, add type hints, "
            "and include docstrings. You write code that fits into an existing "
            "quantitative-research codebase. You NEVER use external dependencies "
            "beyond the Python standard library plus numpy/pandas if absolutely needed."
        )},
        {"role": "user", "content": (
            f"Implement the following capability for DARWIN Labs:\n\n"
            f"Gap: {gap_report.gaps[0] if gap_report.gaps else 'unknown'}\n"
            f"Plan: {gap_report.implementation_plan}\n\n"
            "Write a complete Python module that:\n"
            "1. Is self-contained and importable\n"
            "2. Has a clear public API (functions/classes with docstrings)\n"
            "3. Includes simple usage examples in the module docstring\n"
            "4. Handles edge cases gracefully\n"
            "5. Uses only standard library + numpy (if needed for numerical work)\n\n"
            "Output ONLY the Python code. No markdown fences. No commentary before or after."
        )},
    ]

    try:
        resp = llm.chat(messages, temperature=0.3, max_tokens=2048)
        code = resp.content.strip()
        if code.startswith("```"):
            lines = code.split("\n")
            if lines[0].startswith("```python"):
                lines = lines[1:]
            elif lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].startswith("```"):
                lines = lines[:-1]
            code = "\n".join(lines).strip()
        return code
    except Exception as e:
        return f"# Implementation failed: {e}\n"


def generate_test_code(module_name: str, code: str, llm: Optional[LLMBridge] = None) -> str:
    """Generate pytest-style tests for the new module."""
    llm = llm or LLMBridge()

    messages = [
        {"role": "system", "content": "You write pytest unit tests."},
        {"role": "user", "content": (
            f"Write pytest tests for the following module ({module_name}):\n\n"
            f"{code[:2000]}\n\n"
            "Output ONLY Python test code. No markdown fences."
        )},
    ]

    try:
        resp = llm.chat(messages, temperature=0.2, max_tokens=1024)
        test_code = resp.content.strip()
        if test_code.startswith("```"):
            lines = test_code.split("\n")
            if lines[0].startswith("```python"):
                lines = lines[1:]
            elif lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].startswith("```"):
                lines = lines[:-1]
            test_code = "\n".join(lines).strip()
        return test_code
    except Exception as e:
        return f"# Test generation failed: {e}\n"


def implement(gap_report, llm: Optional[LLMBridge] = None) -> ImplementationResult:
    """Attempt to implement the approved gap.

    Returns file paths created/modified.
    """
    llm = llm or LLMBridge()
    created = []
    modified = []
    tests = []

    if not gap_report.gaps:
        return ImplementationResult(success=False, files_created=[], files_modified=[], tests_added=[], error="No gaps specified")

    # Determine module name from first gap
    gap_slug = gap_report.gaps[0].lower().replace(" ", "_").replace("-", "_")[:40]
    module_name = f"darwin_meta/self_improve/impl_{gap_slug}.py"
    test_name = f"tests/test_{gap_slug}.py"

    module_path = ROOT / module_name
    test_path = ROOT / test_name

    # Don't overwrite existing
    if module_path.exists():
        _backup_file(module_path)
        modified.append(str(module_path))
    else:
        created.append(str(module_path))

    # Generate code
    print(f"[Implementer] Generating code for {gap_report.gaps[0]}...")
    code = generate_module_code(gap_report, llm)
    if code.startswith("# Implementation failed"):
        return ImplementationResult(success=False, files_created=[], files_modified=[], tests_added=[], error=code)

    module_path.parent.mkdir(parents=True, exist_ok=True)
    module_path.write_text(code + "\n")
    print(f"  → wrote {module_path}")

    # Generate tests
    print(f"[Implementer] Generating tests...")
    test_code = generate_test_code(module_name.replace("/", ".").replace(".py", ""), code, llm)
    test_path.parent.mkdir(parents=True, exist_ok=True)
    test_path.write_text(test_code + "\n")
    tests.append(str(test_path))
    print(f"  → wrote {test_path}")

    # Log the improvement
    IMPROVEMENT_LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(IMPROVEMENT_LOG, "a") as f:
        f.write(json.dumps({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "repo": gap_report.repo_name,
            "gap": gap_report.gaps[0],
            "priority": gap_report.priority,
            "confidence": gap_report.confidence,
            "files_created": created,
            "files_modified": modified,
            "tests_added": tests,
        }, ensure_ascii=False) + "\n")

    return ImplementationResult(success=True, files_created=created, files_modified=modified, tests_added=tests)


if __name__ == "__main__":
    # Test with a mock gap
    from darwin_meta.self_improve.gap_analyser import GapReport
    mock = GapReport(
        repo_name="test/repo",
        useful=True,
        confidence=0.8,
        gaps=["Add a volatility regime detector"],
        implementation_plan="Build a module that detects high/low volatility regimes using rolling standard deviation.",
        risk_assessment="Low risk — pure calculation, no external deps.",
        priority="medium",
    )
    result = implement(mock)
    print(result)
