"""DARWIN Self-Improve — GitHub Scout

Searches GitHub for quantitative-finance / trading-strategy repos,
shallow-clones them, and extracts a feature fingerprint.

Uses gh CLI (already authenticated) and caches results locally
so the same repos aren't re-evaluated every run.
"""

from __future__ import annotations

import json
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

CACHE_DIR = Path(__file__).resolve().parent.parent.parent / ".github_scout_cache"
CACHE_DIR.mkdir(exist_ok=True)

# Queries that might surface useful patterns we don't have yet
SEARCH_QUERIES = [
    "quantitative trading strategies python stars:>50",
    "alpha generation backtesting stars:>30",
    "portfolio optimization machine learning stars:>20",
    "statistical arbitrage cointegration stars:>10",
    "options volatility surface python stars:>10",
    "factor investing momentum value stars:>20",
    "crypto market making python stars:>20",
    "risk parity tail risk python stars:>10",
]


@dataclass
class RepoFingerprint:
    full_name: str
    description: str
    stars: int
    language: str
    topics: list[str]
    readme_summary: str          # first 2000 chars of README
    file_tree: list[str]         # top-level + one level deep
    has_backtester: bool
    has_risk_mgmt: bool
    has_data_pipeline: bool
    has_ml: bool
    has_options: bool
    has_crypto: bool
    last_evaluated: str
    eval_count: int = 0          # how many times we've looked at this repo


def _sh(cmd: list[str], cwd: Optional[Path] = None, timeout: int = 60) -> tuple[int, str]:
    p = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout)
    return p.returncode, p.stdout + p.stderr


def search_github(query: str, limit: int = 10) -> list[dict]:
    """Search GitHub repos via gh CLI. Returns list of repo dicts."""
    rc, out = _sh(["gh", "search", "repos", query, "--limit", str(limit), "--json",
                   "fullName,description,stargazersCount,primaryLanguage,topics"])
    if rc != 0:
        print(f"[GitHub Scout] search failed: {out[:200]}")
        return []
    try:
        return json.loads(out)
    except json.JSONDecodeError:
        return []


def _clone_shallow(owner_repo: str, dest: Path) -> bool:
    """Shallow clone a repo (depth 1) for analysis."""
    if dest.exists():
        return True
    rc, out = _sh(["git", "clone", "--depth", "1", f"https://github.com/{owner_repo}.git", str(dest)],
                  timeout=120)
    return rc == 0


def _extract_fingerprint(repo_path: Path, repo_meta: dict) -> RepoFingerprint:
    """Analyse a cloned repo and build a fingerprint."""
    # README summary
    readme_text = ""
    for name in ["README.md", "README.rst", "README.txt", "README"]:
        readme = repo_path / name
        if readme.exists():
            try:
                readme_text = readme.read_text()[:2000]
                break
            except Exception:
                pass

    # File tree (top 2 levels)
    tree = []
    for p in sorted(repo_path.rglob("*")):
        if p.is_file() and len(p.relative_to(repo_path).parts) <= 2:
            tree.append(str(p.relative_to(repo_path)))
        if len(tree) > 100:
            break

    tree_lower = "\n".join(tree).lower()
    has_backtester = any(k in tree_lower for k in ["backtest", "backtester", "simulation"])
    has_risk = any(k in tree_lower for k in ["risk", "drawdown", "var", "cvar", "position"])
    has_data = any(k in tree_lower for k in ["data", "pipeline", "ingest", "fetch"])
    has_ml = any(k in tree_lower for k in ["ml", "model", "predict", "feature", "sklearn", "torch", "tensorflow"])
    has_options = any(k in tree_lower for k in ["option", "volatility", "greeks", "iv"])
    has_crypto = any(k in tree_lower for k in ["crypto", "bitcoin", "exchange", "binance"])

    return RepoFingerprint(
        full_name=repo_meta.get("fullName", ""),
        description=repo_meta.get("description", "") or "",
        stars=repo_meta.get("stargazersCount", 0),
        language=repo_meta.get("primaryLanguage", "") or "",
        topics=repo_meta.get("topics", []) or [],
        readme_summary=readme_text,
        file_tree=tree,
        has_backtester=has_backtester,
        has_risk_mgmt=has_risk,
        has_data_pipeline=has_data,
        has_ml=has_ml,
        has_options=has_options,
        has_crypto=has_crypto,
        last_evaluated=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    )


def load_cache() -> dict[str, RepoFingerprint]:
    cache_file = CACHE_DIR / "repo_cache.json"
    if not cache_file.exists():
        return {}
    raw = json.loads(cache_file.read_text())
    return {k: RepoFingerprint(**v) for k, v in raw.items()}


def save_cache(cache: dict[str, RepoFingerprint]) -> None:
    cache_file = CACHE_DIR / "repo_cache.json"
    cache_file.write_text(json.dumps(
        {k: {**v.__dict__} for k, v in cache.items()},
        indent=2, ensure_ascii=False
    ) + "\n")


def scout(max_repos: int = 5, max_new_clones: int = 3) -> list[RepoFingerprint]:
    """Main entry point: search GitHub, update cache, return candidate repos.

    Args:
        max_repos: max total repos to return
        max_new_clones: max NEW repos to shallow-clone this run
    """
    cache = load_cache()
    all_results: list[RepoFingerprint] = []
    new_cloned = 0

    for query in SEARCH_QUERIES:
        print(f"[GitHub Scout] searching: {query}")
        results = search_github(query, limit=5)
        for repo_meta in results:
            name = repo_meta.get("fullName", "")
            if not name:
                continue
            if name in cache:
                cache[name].eval_count += 1
                all_results.append(cache[name])
                continue
            if new_cloned >= max_new_clones:
                # Still include in results if we have enough metadata
                fp = RepoFingerprint(
                    full_name=name,
                    description=repo_meta.get("description", "") or "",
                    stars=repo_meta.get("stargazersCount", 0),
                    language=repo_meta.get("primaryLanguage", "") or "",
                    topics=repo_meta.get("topics", []) or [],
                    readme_summary="",
                    file_tree=[],
                    has_backtester=False,
                    has_risk_mgmt=False,
                    has_data_pipeline=False,
                    has_ml=False,
                    has_options=False,
                    has_crypto=False,
                    last_evaluated=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                )
                cache[name] = fp
                all_results.append(fp)
                continue

            # Clone and fingerprint
            dest = CACHE_DIR / name.replace("/", "__")
            if _clone_shallow(name, dest):
                fp = _extract_fingerprint(dest, repo_meta)
                fp.eval_count = 1
                cache[name] = fp
                all_results.append(fp)
                new_cloned += 1
                print(f"  → cloned & fingerprinted {name} ({fp.stars}★)")
            else:
                print(f"  → failed to clone {name}")

            if len(all_results) >= max_repos:
                break
        if len(all_results) >= max_repos:
            break

    save_cache(cache)
    # Sort by stars descending, deduplicate
    seen = set()
    deduped = []
    for fp in sorted(all_results, key=lambda x: x.stars, reverse=True):
        if fp.full_name not in seen:
            seen.add(fp.full_name)
            deduped.append(fp)
    return deduped[:max_repos]


if __name__ == "__main__":
    repos = scout()
    print(f"\nScouted {len(repos)} repos:")
    for r in repos:
        flags = []
        if r.has_backtester: flags.append("backtest")
        if r.has_risk_mgmt: flags.append("risk")
        if r.has_data_pipeline: flags.append("data")
        if r.has_ml: flags.append("ml")
        if r.has_options: flags.append("options")
        if r.has_crypto: flags.append("crypto")
        print(f"  {r.full_name} ({r.stars}★) [{', '.join(flags)}]")
