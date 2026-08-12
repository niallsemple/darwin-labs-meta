# DARWIN LABS — Meta-Engine Edition

> **An autonomous discovery laboratory that learns to discover.**

DARWIN Labs is a falsification-first research system for finding exploitable
patterns in data. This edition adds an AI meta-engine: nine LLM-powered
research agents, a meta-learning loop that improves the system over time,
and a daily steering committee that keeps everything on track.

---

## What This Is

The original DARWIN Labs was a manual discovery pipeline:
1. Explorer finds patterns
2. Statistician tests them
3. Sceptic attacks them
4. Gates control promotion
5. Board meeting decides priorities

**The Meta-Engine automates steps 1-5 with AI agents**, then uses a
meta-learning loop to track which agents (and which prompts) produce
better outcomes — and adjusts accordingly.

```
                    DARWIN META-ENGINE
           ┌─────────────────────────────┐
           │  AI Agents (9 roles)        │
           │  ├─ Explorer                │
           │  ├─ Chief Scientist         │
           │  ├─ Statistician            │
           │  ├─ Sceptic                 │
           │  ├─ Execution Engineer      │
           │  ├─ Archaeologist           │
           │  ├─ Risk Officer            │
           │  ├─ Strategy Engineer       │
           │  └─ CEO (board chair)       │
           └─────────────────────────────┘
                        │
           ┌─────────────────────────────┐
           │  Meta-Learning Loop         │
           │  tracks agent performance   │
           │  and adjusts prompts/temps  │
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

This project requires a local OpenAI-compatible server (llama.cpp, Ollama,
etc.) running a capable model. We recommend **Kimi-Linear 48B** at Q2_K_L
(~17 GB, fits in 24 GB RAM).

```bash
# If you have llama.cpp installed:
llama-server -m /path/to/Kimi-Linear-48B-Q2_K_L.gguf -c 4096 --port 8080
```

### 2. Run the AI Daily Pipeline

```bash
cd darwin-labs-ai
python3 scripts/ai_daily_run.py
```

This will:
- Check LLM health
- Run the AI board meeting (agents analyse the library)
- Generate a meta-learning report
- Commit everything to git

### 3. Review the Board Meeting

```bash
cat reports/board-ai-$(date +%Y-%m-%d).md
```

### 4. Steering Committee (once daily)

```bash
export KIMI_API_KEY=your_key
python3 scripts/steering_committee.py
```

---

## Architecture

### `laboratory/` — Core DARWIN Engine

| File | Purpose |
|---|---|
| `schema.py` | Discovery lifecycle, gates, statuses |
| `library_store.py` | JSON-backed Edge Library + Graveyard |
| `stats.py` | Pure-Python falsification statistics |

### `darwin_meta/` — AI Meta-Engine

| Path | Purpose |
|---|---|
| `agents/base_agent.py` | Abstract base with logging |
| `agents/explorer.py` | Generates hypotheses from data |
| `agents/statistician.py` | Statistical evaluation |
| `agents/sceptic.py` | Aggressive attack & falsification |
| `agents/ceo.py` | Strategic synthesis & agenda |
| `loops/meta_learning.py` | Tracks performance, adjusts configs |
| `utils/llm_bridge.py` | Robust OpenAI-compatible client |
| `ai_board_meeting.py` | Orchestrates agents into daily report |

### `scripts/` — Orchestration

| Script | Purpose |
|---|---|
| `ai_daily_run.py` | Full daily pipeline |
| `steering_committee.py` | Daily K3 strategic check |
| `board_meeting.py` | Legacy static report (preserved) |

---

## The Learning Loop

The meta-learning loop (`darwin_meta/loops/meta_learning.py`) is simple but
powerful:

1. **Log** every agent run (prompt, latency, tokens, output summary)
2. **Score** outcomes via human feedback or automated metrics
3. **Adjust** temperature, max_tokens, and strategy based on what worked
4. **Report** trends so you can see which agents improve over time

Feed back outcomes:

```python
from darwin_meta.loops.meta_learning import MetaLearningLoop, AgentScore

loop = MetaLearningLoop()
loop.ingest_outcomes([
    AgentScore("statistician", "h1_review", outcome=0.9, notes=" nailed the p-value concern"),
    AgentScore("sceptic", "h1_review", outcome=0.3, notes="missed the regime-dependency"),
])
```

Then inspect the meta-report:

```python
print(loop.render_report_md())
```

---

## The Nine Agent Roles

| # | Role | AI Class | Output |
|---|---|---|---|
| 1 | **CEO** | `CEOAgent` | Daily agenda, resource allocation, commentary |
| 2 | **Explorer** | `ExplorerAgent` | Candidate discoveries with falsifiable framing |
| 3 | **Chief Scientist** | *(planned)* | Experiment protocols |
| 4 | **Sceptic** | `ScepticAgent` | Attacks, hidden assumptions, kill probability |
| 5 | **Statistician** | `StatisticianAgent` | Significance, concerns, verdict |
| 6 | **Execution Engineer** | *(planned)* | Tradeability assessment |
| 7 | **Archaeologist** | *(planned)* | Lineage links to Library/Graveyard |
| 8 | **Risk Officer** | *(planned)* | Stake caps, kill-switch conditions |
| 9 | **Strategy Engineer** | *(planned)* | Strategy specs & code |

The first five are implemented. The remaining four are scaffolded and
await domain-specific integrations.

---

## Status Lifecycle

```
CANDIDATE → TESTING → SUPPORTED → VALIDATED → SHADOW → MICRO_LIVE → PROMOTED
    └──────────────────── KILLED (graveyard) ──────────────────────┘
```

No discovery promotes itself. Gates are enforced in code by
`laboratory/library_store.py`.

---

## Credits

- **Original DARWIN Labs** by Niall Semple
- **Meta-Engine** built with Kimi-Linear 48B (local) + Kimi K3 (steering)
- **GGUF conversion** by [bartowski](https://huggingface.co/bartowski)
- **Inference** via [llama.cpp](https://github.com/ggml-org/llama.cpp)

---

## License

MIT
