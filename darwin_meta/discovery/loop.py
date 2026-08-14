"""DARWIN Discovery — Autonomous Discovery Loop

Runs the pipeline: adapters → scanners → global BH-FDR → Explorer framing →
new CANDIDATE discoveries in the library. Called daily by ai_daily_run.py.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from darwin_meta.discovery.adapters import ADAPTERS
from darwin_meta.discovery.scanners import SCANNERS, Anomaly
from darwin_meta.utils.llm_bridge import LLMBridge
from darwin_meta.loops.decision_log import log_decision
from laboratory import library_store as store
from laboratory.schema import Discovery
from laboratory.stats import benjamini_hochberg

ROOT = Path(__file__).resolve().parent.parent.parent

LAB_BY_ADAPTER = {
    "equities_daily": "equities",
    "gold_daily": "gold",
    "crypto_1h": "hl_crypto",
}


def _existing_signatures() -> set[str]:
    sigs = set()
    for d in store.load_library() + store.load_graveyard():
        hay = f"{d.title} {d.hypothesis}"
        for marker in ("weekday:", "hour:", "autocorr:"):
            for token in hay.split():
                if token.startswith(marker):
                    sigs.add(token.strip(".,;)"))
        # evidence notes carry the authoritative signature=... tag
        for e in d.evidence:
            for token in e.note.split():
                if token.startswith("signature="):
                    sigs.add(token.split("=", 1)[1].strip(".,;)"))
    return sigs


def _template_candidate(a: Anomaly, lab: str) -> dict:
    """Deterministic hypothesis framing when no LLM is available."""
    direction = "positive" if a.effect > 0 else "negative"
    return {
        "title": f"[AUTO:{a.signature}] {a.description[:80]}",
        "hypothesis": (f"{a.target} shows a {direction} {a.scanner} anomaly: "
                       f"{a.description}. Verified in-sample: effect {a.effect} {a.unit}, "
                       f"n={a.n}, t={a.t}, p={a.p}, survivor of {a.trials_tested} trials at FDR."),
        "falsifiable_prediction": (f"Effect persists out-of-sample with the same sign and "
                                   f">=50% of in-sample magnitude."),
        "kill_criteria": ("Kill if the frozen OOS window shows opposite sign, "
                          "block-bootstrap CI includes 0, or execution costs exceed "
                          "half the gross effect."),
        "data_source": f"{lab} via anomaly scanner '{a.scanner}', window {a.window[0]}→{a.window[1]}",
        "regime_notes": "Unknown — this is a scanner output; regime mapping is the Sceptic's job.",
    }


def _explorer_candidates(survivors: list[Anomaly], lab: str, llm) -> list[dict]:
    """Explorer LLM frames verified anomalies as falsifiable hypotheses.
    Falls back to the deterministic template if the LLM is down or
    returns nothing usable."""
    context = {
        "verified_anomalies": [
            {
                "signature": a.signature, "target": a.target,
                "description": a.description, "effect": a.effect, "unit": a.unit,
                "n": a.n, "t_stat": a.t, "p_value": a.p,
                "trials_tested": a.trials_tested, "window": a.window,
            }
            for a in survivors
        ],
        "instruction": ("These anomalies are VERIFIED scanner output with real statistics. "
                        "Frame each as a falsifiable hypothesis. Do not assert truth. "
                        "Keep the signature in the title as [AUTO:<signature>]."),
    }
    try:
        from darwin_meta.agents.explorer import ExplorerAgent
        agent = ExplorerAgent(llm)
        cands = agent.run(json.dumps(context, indent=2), max_candidates=len(survivors))
        usable = [c for c in cands if c.get("hypothesis") and c.get("kill_criteria")]
        if usable:
            return usable
    except Exception as e:
        print(f"  [Discovery] Explorer LLM failed ({e}) — using template framing")
    return [_template_candidate(a, lab) for a in survivors]


def run_discovery_loop(llm: Optional[LLMBridge] = None,
                       labs: tuple[str, ...] = ("equities_daily", "gold_daily", "crypto_1h"),
                       max_new_candidates: int = 3,
                       alpha: float = 0.05) -> dict:
    """One autonomous discovery run. Returns a summary dict."""
    summary = {"timestamp": datetime.now(timezone.utc).isoformat(),
               "labs": {}, "tests_run": 0, "anomalies": 0,
               "fdr_survivors": 0, "new_candidates": [], "skipped_duplicates": 0}

    # 1+2. Data → deterministic scans
    all_anomalies: list[tuple[str, Anomaly]] = []  # (lab, anomaly)
    for lab in labs:
        adapter = ADAPTERS.get(lab)
        if adapter is None:
            summary["labs"][lab] = "unknown adapter"
            continue
        data = adapter()
        n_series = len(data["series"])
        if not n_series:
            summary["labs"][lab] = "no data"
            continue
        before = len(all_anomalies)
        for scan in SCANNERS.values():
            for a in scan(data):
                all_anomalies.append((LAB_BY_ADAPTER.get(lab, lab), a))
        summary["labs"][lab] = f"{n_series} series, {len(all_anomalies) - before} tests"

    summary["tests_run"] = len(all_anomalies)
    summary["anomalies"] = len(all_anomalies)
    if not all_anomalies:
        return summary

    # 3. GLOBAL multiple-testing control: every test counts
    pvals = [a.p if a.p is not None else 1.0 for _, a in all_anomalies]
    bh = benjamini_hochberg(pvals, alpha=alpha)
    survivors = []
    for idx in bh["rejected"]:
        lab, a = all_anomalies[idx]
        a.fdr_significant = True
        a.trials_tested = len(all_anomalies)
        survivors.append((lab, a))
    survivors.sort(key=lambda x: x[1].p or 1.0)
    summary["fdr_survivors"] = len(survivors)

    # 4. Dedupe against everything Darwin has ever seen
    existing = _existing_signatures()
    fresh = [(lab, a) for lab, a in survivors if a.signature not in existing]
    summary["skipped_duplicates"] = len(survivors) - len(fresh)
    fresh = fresh[:max_new_candidates]

    # 5. Explorer frames hypotheses (LLM or template fallback)
    if fresh:
        by_lab: dict[str, list[Anomaly]] = {}
        for lab, a in fresh:
            by_lab.setdefault(lab, []).append(a)
        for lab, anomalies in by_lab.items():
            candidates = _explorer_candidates(anomalies, lab, llm)
            for a, cand in zip(anomalies, candidates):
                _register_candidate(lab, a, cand, summary)

    _write_report(summary, all_anomalies, survivors, alpha)
    return summary


def _register_candidate(lab: str, a: Anomaly, cand: dict, summary: dict) -> None:
    d = Discovery(
        id="",
        title=cand.get("title", f"[AUTO:{a.signature}]")[:120],
        lab=lab,
        status="CANDIDATE",
        hypothesis=cand.get("hypothesis", ""),
        falsifiable_prediction=cand.get("falsifiable_prediction", ""),
        kill_criteria=cand.get("kill_criteria", ""),
        regime_notes=cand.get("regime_notes", ""),
    )
    d = store.add(d)
    store.add_evidence(
        d.id, author="anomaly_engine",
        note=(f"scanner={a.scanner} signature={a.signature} effect={a.effect} {a.unit} "
              f"n={a.n} t={a.t} p={a.p} trials_tested={a.trials_tested} "
              f"window={a.window[0]}→{a.window[1]}"),
        kind="experiment")
    log_decision("explorer", d.id, "propose",
                 {"signature": a.signature, "p": a.p, "trials_tested": a.trials_tested})
    summary["new_candidates"].append({"id": d.id, "title": d.title,
                                      "signature": a.signature, "p": a.p})
    print(f"  [Discovery] NEW CANDIDATE {d.id}: {a.signature} (p={a.p})")


def _write_report(summary: dict, all_anomalies, survivors, alpha: float) -> None:
    path = ROOT / "reports" / f"discovery-{datetime.now(timezone.utc).strftime('%Y-%m-%d')}.md"
    L = [f"# DARWIN Discovery Run — {summary['timestamp'][:10]}", ""]
    L.append(f"- Tests run: **{summary['tests_run']}** "
             f"({', '.join(f'{k}: {v}' for k, v in summary['labs'].items())})")
    L.append(f"- Global BH step-up at FDR {alpha}: **{summary['fdr_survivors']} survivors**")
    L.append(f"- Already known (skipped): {summary['skipped_duplicates']}")
    L.append(f"- New candidates registered: {len(summary['new_candidates'])}")
    L.append("")
    if summary["new_candidates"]:
        L.append("## New candidates")
        for c in summary["new_candidates"]:
            L.append(f"- **{c['id']}** `{c['signature']}` — p={c['p']}")
        L.append("")
    if survivors:
        L.append("## All FDR survivors (incl. known)")
        for lab, a in survivors[:15]:
            L.append(f"- `{a.signature}` [{lab}] — {a.description} "
                     f"(effect {a.effect} {a.unit}, n={a.n}, t={a.t}, p={a.p})")
        L.append("")
    L.append("## Strongest non-survivors (killed by FDR)")
    rest = sorted([a for _, a in all_anomalies if not a.fdr_significant and a.p is not None],
                  key=lambda x: x.p)[:5]
    for a in rest:
        L.append(f"- `{a.signature}` — p={a.p} did not survive {a.trials_tested or summary['tests_run']} trials")
    L.append("")
    L.append("---")
    L.append("*Deterministic scanner output. LLMs frame hypotheses; they never assert findings.*")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(L) + "\n")


if __name__ == "__main__":
    print(json.dumps(run_discovery_loop(), indent=2))
