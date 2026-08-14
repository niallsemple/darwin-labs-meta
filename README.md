# DARWIN LABS — Meta-Engine Edition

> **An autonomous discovery laboratory that learns to discover.**

This repo (`darwin-labs-ai` / `darwin-labs-meta`) is the **AI meta-engine** that sits on top of the core [DARWIN Labs](https://github.com/niallsemple/darwin-labs) system. It automates the research pipeline with LLM-powered agents, tracks which agents and prompts produce better outcomes, and runs a self-improvement loop that scouts GitHub for new ideas — all sandboxed so `main` is never touched automatically.

---

## What This Is

The original DARWIN Labs is a manual discovery pipeline:
1. Explorer finds patterns
2. Statistician tests them
3. Sceptic attacks them
4. Gates control promotion
5. Board meeting decides priorities

**The Meta-Engine automates steps 1-5 with AI agents**, then uses a meta-learning loop to track which agents (and which prompts) produce better outcomes — and adjusts accordingly. A self-improvement engine scouts open-source repos, evaluates gaps against DARWIN's capabilities, and proposes implementations as pull requests.

```
                    DARWIN META-ENGINE
           ┌─────────────────────────────┐
           │  AI Agents (6 implemented)  │
           │  ├─ CEO (board chair)       │
           │  ├─ Explorer                │
           │  ├─ Statistician            │
           │  ├─ Sceptic                 │
           │  ├─ Archaeologist           │
           │  └─ BaseAgent (framework)   │
           └─────────────────────────────┘
                        │
           ┌─────────────────────────────┐
           │  Autonomous Discovery Loop  │
           │  deterministic scan → LLM   │
           │  hypothesis framing         │
           └─────────────────────────────┘
                        │
           ┌─────────────────────────────┐
           │  Decay Detection            │
           │  (re-evaluates SUPPORTED+)  │
           └─────────────────────────────┘
                        │
           ┌─────────────────────────────┐
           │  Meta-Learning Loop         │
           │  tracks agent performance   │
           │  and adjusts prompts/temps  │
           └─────────────────────────────┘
                        │
           ┌─────────────────────────────┐
           │  Self-Improvement Engine    │
           │  GitHub scout → gap analyse │
           │  → implement → sandbox PR   │
           └─────────────────────────────┘
                        │
           ┌─────────────────────────────┐
           │  Steering Committee (K3)    │
           │  daily strategic review     │
           └─────────────────────────────┘
```

---

## Quick Start

### 1. Start the Local LLM

This project requires a local OpenAI-compatible server (llama.cpp, Ollama, etc.) running a capable model. We recommend **Kimi-Linear 48B** at Q2_K_L (~17 GB, fits in 24 GB RAM).

```bash
# If you have llama.cpp installed:
llama-server -m /path/to/Kimi-Linear-48B-Q2_K_L.gguf -c 4096 --port 8080
```

### 2. Run the AI Daily Pipeline

```bash
cd darwin-labs-ai
python3 scripts/ai_daily_run.py
```

This runs the full pipeline:
1. **LLM health check**
2. **Decay detection** — re-evaluates SUPPORTED+ discoveries with real returns
3. **Autonomous discovery loop** — deterministic anomaly scan + LLM hypothesis framing
4. **AI board meeting** — agents analyse the library and produce an agenda
5. **HTML dashboard** — self-contained, no dependencies
6. **Meta-learning + outcome attribution** — real outcomes drive prompt evolution
7. **Self-improvement cycle** — sandboxed: branch + PR, `main` untouched
8. **Git commit + push**

### 3. Review the Board Meeting

```bash
cat reports/board-ai-$(date +%Y-%m-%d).md
```

### 4. Open the Dashboard

```bash
open reports/dashboard.html
```

### 5. Steering Committee (once daily)

```bash
export KIMI_API_KEY=your_key
python3 scripts/steering_committee.py
```

---

## Architecture

### `laboratory/` — Core DARWIN Engine (shared with darwin-labs)

| File | Purpose |
|---|---|
| `schema.py` | Discovery lifecycle, gates, statuses |
| `library_store.py` | JSON-backed Edge Library + Graveyard |
| `stats.py` | Pure-Python falsification statistics |
| `experiment.py` | Experiment orchestration |

### `darwin_meta/` — AI Meta-Engine

#### `agents/` — LLM-Powered Research Roles

| File | Role | Status | Output |
|---|---|---|---|
| `ceo.py` | **CEO** | ✅ Implemented | Daily agenda, resource allocation, commentary |
| `explorer.py` | **Explorer** | ✅ Implemented | Candidate discoveries with falsifiable framing |
| `statistician.py` | **Statistician** | ✅ Implemented | Statistical evaluation + verdict |
| `sceptic.py` | **Sceptic** | ✅ Implemented | Aggressive attack & falsification |
| `archaeologist.py` | **Archaeologist** | ✅ Implemented | Lineage links, Graveyard mining |
| `base_agent.py` | Base class | ✅ Framework | Logging, LLM bridge, structured output |

**Scaffolded (awaiting domain-specific integration):**
- Chief Scientist — experiment protocol design
- Execution Engineer — tradeability assessment
- Risk Officer — live-capital gate
- Strategy Engineer — strategy specs & code generation

#### `loops/` — System Intelligence

| File | Purpose |
|---|---|
| `meta_learning.py` | Tracks agent performance, adjusts temps/prompts/strategies |
| `outcome_attribution.py` | Attributes real-world outcomes to agent decisions |
| `decay_detection.py` | Re-evaluates SUPPORTED+ discoveries for decay signals |
| `decision_log.py` | Immutable decision journal |
| `meta_state.json` | Persisted meta-learning state |

**Decay signals tracked:**
- Stale evidence (>14 days)
- Effect size shrinkage (>50%)
- Negative recent Sharpe
- Max drawdown >10%
- Stuck in SUPPORTED >30 days

#### `self_improve/` — Autonomous Enhancement

| File | Purpose |
|---|---|
| `github_scout.py` | Scouts GitHub repos for relevant strategies/techniques |
| `gap_analyser.py` | Evaluates repos against DARWIN capabilities (local LLM) |
| `implementer.py` | Generates implementations from approved gaps |
| `sandbox.py` | Self-improve sandbox: branch → validate → PR |
| `edge_tracker.py` | Before/after snapshots of discovery counts |
| `loop.py` | Orchestrates one self-improvement cycle |

**Safety:** All self-improvement happens on a `self-improve/*` branch. The sandbox validates, commits, and opens a PR. `main` is never touched automatically.

#### `discovery/` — Autonomous Discovery

| File | Purpose |
|---|---|
| `loop.py` | Deterministic anomaly scan + LLM hypothesis framing |
| `scanners.py` | Data scanners (price, volume, funding, etc.) |
| `adapters.py` | Data source adapters |

#### `utils/` — Infrastructure

| File | Purpose |
|---|---|
| `llm_bridge.py` | Robust OpenAI-compatible client with retries |
| `dashboard.py` | Self-contained HTML dashboard generator |
| `returns_adapter.py` | Maps real returns to discoveries for decay detection |

### `scripts/` — Orchestration

| Script | Purpose |
|---|---|
| `ai_daily_run.py` | **Full daily pipeline** (8 steps, see above) |
| `steering_committee.py` | Daily K3 strategic check |
| `run_demo.py` | Demo run for testing |

### `library/` — Live Data

| File | Purpose |
|---|---|
| `edges.json` | Live discoveries (synced with darwin-labs) |
| `graveyard.json` | Killed discoveries |
| `returns_sources.json` | Attribution mapping for real returns |

---

## The Learning Loops

### Meta-Learning Loop

```python
from darwin_meta.loops.meta_learning import MetaLearningLoop, AgentScore

loop = MetaLearningLoop()
loop.ingest_outcomes([
    AgentScore("statistician", "h1_review", outcome=0.9, notes="nailed the p-value concern"),
    AgentScore("sceptic", "h1_review", outcome=0.3, notes="missed the regime-dependency"),
])
print(loop.render_report_md())
```

Tracks per-agent success rates, latency, token usage, and outcome quality. Adjusts temperature and strategy based on what worked.

### Outcome Attribution

Links real-world returns (from live or shadow strategies) back to the agent decisions that produced them. This closes the loop: agents don't just get scored on output quality — they get scored on **actual edge production**.

### Decay Detection

Periodically re-evaluates all SUPPORTED/VALIDATED/SHADOW discoveries:

| Score | Action |
|---|---|
| 0.0-0.2 | 🟢 Healthy |
| 0.2-0.4 | 🟡 Watch |
| 0.4-0.7 | 🟠 Investigate |
| 0.7+ | 🔴 Escalate to board meeting |

### Self-Improvement Cycle

```
[1] Take before snapshot
[2] Scout GitHub (max 3 repos)
[3] Evaluate gaps with local LLM
[4] If approved (confidence ≥ 0.7), implement in sandbox
[5] Validate, commit to branch, open PR
[6] Take after snapshot
[7] Generate report
```

---

## Status Lifecycle

Same as core DARWIN Labs:

```
CANDIDATE → TESTING → SUPPORTED → VALIDATED → SHADOW → MICRO_LIVE → PROMOTED
    └──────────────────── KILLED (graveyard) ──────────────────────┘
```

No discovery promotes itself. Gates are enforced in code by `laboratory/library_store.py`.

---

## Dashboard

A self-contained HTML dashboard is generated daily at `reports/dashboard.html`. No external dependencies — pure HTML/CSS/JS.

**Sections:**
- Live discovery count, graveyard count, survival rate
- Status breakdown with progress bars
- Full live discovery table (ID, title, lab, status, effect, n, p-value)
- Recent graveyard entries with kill causes
- Decay signals with severity
- Agent performance (last 50 runs, success rate, latency, health)

---

## Relationship to Core DARWIN Labs

```
      darwin-labs-ai (this repo)          darwin-labs (core repo)
      ─────────────────────────           ─────────────────────────
      AI agents, meta-learning            29 human-readable roles
      Autonomous discovery                Manual + connected labs
      Self-improvement engine             Strategy registry
      HTML dashboard                      Edge Library + Graveyard
      
               │                                │
               └────────── shared library ──────┘
               (edges.json, graveyard.json,
                returns_sources.json)
```

The meta-engine reads and writes the same `library/` JSON files as the core system. You can run either pipeline (or both) — they converge on the same Edge Library.

---

## Founding Rules

1. **Every hypothesis must be falsifiable before it enters the library.**
2. **In-sample backtests confirm hypotheses; they never validate them.** Validation is out-of-sample or it is nothing.
3. **Multiple-testing correction is not optional** (BH-FDR in `stats.py`).
4. **Execution-adjusted results are the only results that count for promotion.**
5. **The Graveyard is as valuable as the Library** — failed ideas are memory.
6. **Freeze before you trust.** Out-of-sample windows are frozen at discovery time.
7. **No agent promotes its own discovery.** Independent gate approvals required.
8. **Self-improvement is sandboxed.** `main` is never touched automatically.

---

## Credits

- **Original DARWIN Labs** by Niall Semple
- **Meta-Engine** built with Kimi-Linear 48B (local) + Kimi K3 (steering)
- **GGUF conversion** by [bartowski](https://huggingface.co/bartowski)
- **Inference** via [llama.cpp](https://github.com/ggml-org/llama.cpp)

---

## License

MIT
