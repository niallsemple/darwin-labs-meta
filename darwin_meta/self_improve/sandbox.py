"""DARWIN Self-Improve — Sandbox

Darwin no longer modifies itself on main. Implementations happen on a
throwaway branch and may only reach GitHub as a pull request:

1. ensure_branch()  — create self-improve/YYYY-MM-DD from the current branch
2. register()       — declare which files the implementer created/modified
3. finalise()       — verify protected files untouched, compile every
                      generated module, run generated tests, commit ONLY the
                      registered files, push the branch, open a PR via `gh`
                      (if installed), then return to the original branch
4. abort()          — roll everything back: delete generated files, restore
                      .bak backups, return to the original branch

Nothing the LLM writes can reach main without a human merging the PR.
"""

from __future__ import annotations

import fnmatch
import py_compile
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

# Generated code may ONLY live in these places. Anything else is protected.
ALLOWED_PATTERNS = [
    "darwin_meta/self_improve/impl_*.py",
    "tests/test_*.py",
    "*.bak_*",  # timestamped backups the implementer makes before overwrites
]

ROOT = Path(__file__).resolve().parent.parent.parent


class SandboxError(Exception):
    pass


def _sh(cmd: list[str], timeout: int = 120) -> tuple[int, str]:
    p = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, timeout=timeout)
    return p.returncode, (p.stdout + p.stderr)


def _allowed(relpath: str) -> bool:
    return any(fnmatch.fnmatch(relpath, pat) for pat in ALLOWED_PATTERNS)


class SelfImproveSandbox:
    def __init__(self) -> None:
        self.branch: str | None = None
        self.base_branch: str | None = None
        self.registered: list[str] = []
        self.pr_url: str = ""

    # ------------------------------------------------------------------
    def ensure_branch(self) -> str:
        """Create (once) the working branch for this cycle."""
        if self.branch:
            return self.branch
        rc, out = _sh(["git", "rev-parse", "--abbrev-ref", "HEAD"])
        if rc != 0:
            raise SandboxError(f"cannot determine current branch: {out}")
        self.base_branch = out.strip()
        stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        name = f"self-improve/{stamp}"
        rc, out = _sh(["git", "checkout", "-qb", name])
        if rc != 0:  # branch exists from an earlier run today
            name = f"self-improve/{stamp}-{datetime.now(timezone.utc).strftime('%H%M%S')}"
            rc, out = _sh(["git", "checkout", "-qb", name])
            if rc != 0:
                raise SandboxError(f"cannot create branch: {out}")
        self.branch = name
        print(f"  [Sandbox] on branch {name} (base: {self.base_branch})")
        return name

    def register(self, relpaths: list[str]) -> None:
        self.registered.extend(str(p) for p in relpaths)

    # ------------------------------------------------------------------
    def _validate(self) -> list[str]:
        """Return list of problems; empty means safe to commit."""
        problems = []
        # Protected-file check: every registered path must be in an allowed place
        for rel in self.registered:
            if not _allowed(rel):
                problems.append(f"protected path touched: {rel}")
        # Compile check on every generated module
        for rel in self.registered:
            p = ROOT / rel
            if p.suffix == ".py" and p.exists() and not p.name.endswith((".bak",)) and ".bak_" not in p.name:
                try:
                    py_compile.compile(str(p), doraise=True)
                except py_compile.PyCompileError as e:
                    problems.append(f"compile failed for {rel}: {e}")
        return problems

    def _run_tests(self) -> list[str]:
        """Run pytest on generated test files. Missing pytest = skip with note;
        failing tests = problem."""
        problems = []
        if not shutil.which("pytest") and not _module_available("pytest"):
            print("  [Sandbox] pytest not available — compile check only")
            return problems
        for rel in self.registered:
            p = ROOT / rel
            if rel.startswith("tests/") and p.suffix == ".py" and p.exists():
                rc, out = _sh(["python3", "-m", "pytest", rel, "-x", "-q"], timeout=180)
                if rc != 0:
                    problems.append(f"tests failed for {rel}: {out[-400:]}")
        return problems

    # ------------------------------------------------------------------
    def finalise(self) -> dict:
        """Validate, commit, push, open PR, return to base branch."""
        if not self.branch or not self.registered:
            return {"active": False, "reason": "no implementations this cycle"}

        problems = self._validate() + self._run_tests()
        if problems:
            for p in problems:
                print(f"  [Sandbox] REJECT: {p}")
            self.abort("validation failed: " + "; ".join(problems[:3]))
            return {"active": True, "committed": False, "problems": problems}

        # Commit ONLY the registered files — never `git add -A`
        existing = [r for r in self.registered if (ROOT / r).exists()]
        if not existing:
            self.abort("no registered files on disk")
            return {"active": True, "committed": False, "problems": ["no files"]}
        _sh(["git", "add", "--"] + existing)
        rc, out = _sh(["git", "-c", "user.name=darwin-meta",
                       "-c", "user.email=darwin@local", "commit", "-qm",
                       f"self-improve proposal: {datetime.now(timezone.utc).strftime('%Y-%m-%d')} "
                       f"({len(existing)} files, sandbox-validated)"])
        if rc != 0:
            self.abort(f"commit failed: {out[:200]}")
            return {"active": True, "committed": False, "problems": [out[:200]]}

        rc, out = _sh(["git", "push", "-u", "origin", self.branch])
        pushed = rc == 0
        print(f"  [Sandbox] branch {self.branch} {'pushed' if pushed else 'push FAILED: ' + out[:150]}")

        pr_url = ""
        if pushed and shutil.which("gh"):
            rc, out = _sh(["gh", "pr", "create", "--fill", "--head", self.branch,
                           "--title", f"DARWIN self-improve proposal {datetime.now(timezone.utc).strftime('%Y-%m-%d')}",
                           "--body", "Generated by the DARWIN self-improvement engine. "
                                     "Sandbox-validated (protected files, compile, tests). "
                                     "Human review required before merge."])
            if rc == 0:
                pr_url = out.strip().splitlines()[-1] if out.strip() else ""
                print(f"  [Sandbox] PR opened: {pr_url}")
            else:
                print(f"  [Sandbox] gh pr create failed: {out[:150]}")

        self._return_to_base()
        return {"active": True, "committed": True, "branch": self.branch,
                "pushed": pushed, "pr_url": pr_url,
                "note": "proposal on branch/PR — main untouched until a human merges"}

    def abort(self, reason: str) -> None:
        """Roll back everything this cycle tried to change."""
        print(f"  [Sandbox] ABORT ({reason}) — rolling back")
        for rel in self.registered:
            p = ROOT / rel
            if ".bak_" in p.name:
                continue
            if p.exists():
                p.unlink()  # delete generated file
            # restore any backup of this file
            for bak in sorted(p.parent.glob(p.name + ".bak_*")):
                shutil.copy2(bak, p)
        self._return_to_base(delete_branch=True)

    def _return_to_base(self, delete_branch: bool = False) -> None:
        if self.base_branch:
            rc, out = _sh(["git", "checkout", "-q", self.base_branch])
            if rc != 0:
                print(f"  [Sandbox] WARNING: could not return to {self.base_branch}: {out[:150]}")
        if delete_branch and self.branch:
            _sh(["git", "branch", "-qD", self.branch])


def _module_available(name: str) -> bool:
    rc, _ = _sh(["python3", "-c", f"import {name}"])
    return rc == 0
