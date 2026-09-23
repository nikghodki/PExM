# PExM

### Predictive Experience Model — memory for AI agents that learns, not just stores.

<p align="center">
  <img src="assets/demo.gif" width="800" alt="PExM demo: absorb experiences, query for context, check novelty">
  <br><em>A real session. The agent absorbs coding experiences, queries for context, and detects novel information — all in model weights, no database.</em>
</p>

---

## Connect Your Agent in 30 Seconds

PExM runs as a server. Your agent talks to it via **MCP** or **HTTP**.

### Claude Code

Add to `.claude/settings.json`:
```json
{
  "mcpServers": {
    "pexm": {
      "command": "python",
      "args": ["-m", "pexm.serve.mcp_server"],
      "cwd": "/path/to/PExM",
      "env": {"PYTHONPATH": "/path/to/PExM"}
    }
  }
}
```

Your agent gets three tools: `pexm_absorb`, `pexm_query`, `pexm_surprise`.

### OpenClaw / Codex

Same MCP config — add the server to your MCP settings. See [integrations/](integrations/) for copy-paste configs.

### Any Other Agent (CrewAI, LangGraph, Hermes, custom)

Start the HTTP server:
```bash
PYTHONPATH=. python -m pexm.serve.http_server --port 7437
```

Then from your agent:
```
POST /absorb   {"state": "debugging auth", "outcome": "JWT expires after 3600s"}
POST /query    {"state": "fixing token expiry in tests"}
POST /surprise {"state": "...", "outcome": "..."}
```

Returns readable text your agent can inject directly into its prompt.

---

## What Your Agent Sees

When your agent calls `pexm_query("fixing auth token expiry in tests")`, it gets back:

```
3 tests failed in test_auth.py. Token expiry causes mid-suite failures.
JWT tokens with RS256 signing. Expire after 3600 seconds. Refresh tokens in Redis.
alice refactored auth to async handlers. bob added rate limiting to login.
```

Ranked by relevance. Ready to paste into context. No configuration.

When your agent learns something new, it calls `pexm_absorb`:

```
> pexm_absorb("debugging auth", "JWT tokens expire after 3600s")
Absorbed. Surprise: 0.72. Stored: 43 experiences.
```

High surprise = novel information, large update to model weights.
Low surprise = already known, tiny update.

---

## Why PExM, Not a Vector Store?

Every agent memory today stores text in a database and retrieves by similarity. PExM is different: **the model's weights are the memory**. Absorbing an experience updates the weights. Querying runs a forward pass.

| | Vector Store | PExM |
|---|---|---|
| **Store** | Save text + embedding | `absorb()` updates model weights |
| **Retrieve** | Cosine similarity search | `query()` synthesizes from learned patterns |
| **Evict** | LRU / score / manual policy | Natural forgetting via weight interference |
| **Stale data** | Stays until manually removed | Contradictions overwrite automatically |
| **Novel detection** | Not supported | `surprise()` tells you before you store |
| **Latency at scale** | Grows with memory size | Constant (~130ms at any scale) |

### Benchmarks

500 coding experiences across 6 domains. Full reproduction: `python -m pexm.benchmarks.run_full_benchmark`.

| Experiences | PExM | Vector Store | PExM Wins | PExM Latency | Vector Latency |
|---:|---:|---:|---:|---:|---:|
| 50 | 0.975 | 0.938 | 8/8 | 119ms | 169ms |
| 100 | 0.978 | 0.944 | 8/8 | 117ms | 237ms |
| 200 | 0.977 | 0.935 | 8/8 | 119ms | 352ms |
| 500 | 0.979 | 0.937 | 8/8 | 118ms | 797ms |

PExM generate latency stays flat. Vector store retrieval grows linearly.

> **Honest limitation:** With fewer than 50 experiences, PExM underperforms vector retrieval. The model needs data to learn from. Below 50, use a vector store.

---

## Install

```bash
git clone https://github.com/nikghodki/PExM.git
cd PExM
pip install torch transformers safetensors numpy
```

Requires Python 3.9+. Works on Apple Silicon (MPS) and NVIDIA GPUs (CUDA).

### Start the Server

```bash
# MCP (for Claude Code, OpenClaw, Codex)
PYTHONPATH=. python -m pexm.serve.mcp_server

# HTTP (for everything else)
PYTHONPATH=. python -m pexm.serve.http_server --port 7437
```

### Run the Demo

```bash
PYTHONPATH=. python examples/demo.py
```

### Run the Benchmarks

```bash
PYTHONPATH=. python -m pexm.benchmarks.generate_corpus
PYTHONPATH=. python -m pexm.benchmarks.run_full_benchmark
```

---

## How It Works

```
Agent has an experience          Agent needs context
        |                                |
        v                                v
   model.absorb()                  model.query()
        |                                |
   Prediction error             Cosine search over
   drives gated update          learned embeddings
        |                                |
   High surprise =              Returns ranked text
   large update                 ready for the prompt
        |
   Low surprise =
   tiny update
```

**Multi-timescale streams**: Three adaptation layers at different learning rates. Fast stream captures what happened this session. Slow stream accumulates patterns across projects. Tiers emerge from learning rates, not from configuration.

**Surprise gating**: Before updating weights, the model predicts the outcome. The prediction error controls how much the weights change. Novel experiences get large updates. Familiar patterns barely move the weights.

**Natural forgetting**: When you absorb "auth now uses OAuth2" after the model learned "auth uses JWT," the new experience overwrites the old prediction. No staleness detector. No manual eviction.

---

## Integrations

| Framework | Method | Setup |
|---|---|---|
| Claude Code | MCP server | [Config](integrations/README.md#claude-code) |
| OpenClaw | MCP server | [Config](integrations/README.md#openclaw) |
| Codex | MCP server | [Config](integrations/README.md#codex) |
| CrewAI | HTTP API | [Example](integrations/README.md#crewai) |
| LangGraph | HTTP API | [Example](integrations/README.md#langgraph) |
| Hermes | HTTP API | [Example](integrations/README.md#hermes--custom-agents) |
| Custom | HTTP API | `POST /absorb`, `POST /query`, `POST /surprise` |

---

## API

### `absorb(state, outcome)`
Absorb an experience. Returns surprise score.

### `query(state, top_k=5)`
Query for relevant context. Returns ranked text.

### `surprise(state, outcome)`
Check novelty. Returns 0 (familiar) to 1 (novel).

### `is_novel(state, outcome, threshold=0.6)`
Quick boolean check: worth absorbing?

Full API docs in [pexm/core/experience_model.py](pexm/core/experience_model.py).

---

## Limitations

- **Needs ~50 experiences** to outperform vector retrieval. Below that, use a vector store.
- **Absorb latency ~270ms** per experience (includes backward pass). Use background absorption for inline agents.
- **Single agent** — no multi-agent memory sharing yet.
- **Surprise calibration** needs ~100 experiences for reliable novelty detection.

---

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). High-impact areas:

- Real-world agent integrations and examples
- Scale testing beyond 500 experiences
- Persistence (save/load model state)
- Multi-agent memory sharing

---

## Citation

```bibtex
@misc{pexm2026,
  title={PExM: Predictive Experience Models for AI Agent Memory},
  year={2026},
  howpublished={\url{https://github.com/nikghodki/PExM}},
}
```

## License

Apache-2.0
