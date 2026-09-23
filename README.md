# PExM

**Predictive Experience Model — memory that lives in the weights, not in a database.**

PExM is a new approach to AI agent memory. Instead of storing memories as text in a vector store and retrieving them by similarity, PExM absorbs experiences directly into model weights. Querying produces synthesized context from everything the model has learned — not a lookup, but a generation.

```
Traditional agent memory:     Agent -> query -> [Vector DB] -> retrieve text -> Agent
                                                  |
                                            store / evict / rerank (heuristics)

PExM:                         Agent -> state -> [Experience Model] -> synthesized context -> Agent
                                                      |
                                                absorb experience (weight update)
```

No store. No retrieval. No eviction policy. Two operations: **absorb** and **generate**.

---

## Why

Every agent memory system today — Mem0, LangGraph, CrewAI, Letta — treats memory as **dead data** in a store. They differ only in how they manage that store: better retrieval, smarter eviction, fancier embeddings.

This approach has a fundamental problem: [memories degrade when managed](https://arxiv.org/abs/2605.12978). The more you consolidate, merge, and rewrite memories, the worse they get.

PExM takes a different approach. The model's weights **are** the memory. Experiencing something **is** remembering it. Contradictions resolve through weight interference — no staleness detector needed.

| Problem | Store-based solution | PExM solution |
|---|---|---|
| What to store? | Classifier decides | Everything absorbs; surprise controls update magnitude |
| What to retrieve? | Cosine similarity | Forward pass synthesizes across all knowledge |
| What to evict? | LRU / score / policy | Natural forgetting via weight interference |
| Stale memories? | Staleness detector | New experiences overwrite old predictions |
| Redundant memories? | Dedup / merge | Repeated experiences reinforce existing weights |
| Scales with memory size? | Retrieval slows linearly | **Generation time is constant** |

---

## Benchmarks

All benchmarks on Apple Silicon (MPS). 500 synthetic coding experiences across 6 domains, 50 held-out novel experiences, 8 test queries. Full reproduction: `PYTHONPATH=. python pexm/benchmarks/run_full_benchmark.py`.

### Scaling Behavior

PExM needs ~50 experiences to surpass vector retrieval. After that, quality holds steady while vector store latency grows linearly.

| Experiences | PExM | Vector Store | Delta | Wins | Generate | Retrieve | Surprise Sep |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 10 | 0.865 | 0.935 | -0.070 | 0/8 | 118ms | 127ms | -0.064 |
| 50 | 0.975 | 0.938 | +0.037 | 8/8 | 119ms | 169ms | +0.015 |
| 100 | 0.978 | 0.944 | +0.034 | 8/8 | 117ms | 237ms | +0.045 |
| 200 | 0.977 | 0.935 | +0.042 | 8/8 | 119ms | 352ms | +0.021 |
| 500 | 0.979 | 0.937 | +0.042 | 8/8 | 118ms | 797ms | +0.101 |

- **Context quality**: PExM +0.042 over vector store at 500 experiences, winning 8/8 queries
- **Generate latency is constant**: 118ms at every scale. Vector retrieve grows 127ms to 797ms (6.3x)
- **Surprise calibration improves with scale**: separation +0.101 at 500 experiences
- **Forgetting works at every scale**: contradictions displace stale knowledge

### Conversational Memory (Multi-Turn Recall)

PExM is designed for **synthesis across many experiences**, not verbatim episode lookup. On a LoCoMo-style multi-turn recall task (3 sessions, 9 queries asking about specific events):

| Method | Recall Similarity | Queries Won |
|---|---:|---:|
| Vector Store | 0.957 | **9/9** |
| PExM | 0.703 | 0/9 |

Vector store wins here because conversational recall needs exact episode retrieval ("who fixed the bug?" needs the exact commit message). PExM blends across all absorbed knowledge and loses specific details. This is an intentional tradeoff: PExM excels when the answer **spans multiple experiences** (the scaling benchmark), not when it lives in one specific memory.

### When to Use PExM vs a Vector Store

| Scenario | Better choice | Why |
|---|---|---|
| "What do I need to know about auth?" | **PExM** | Synthesizes across many experiences |
| "Who pushed commit abc123?" | **Vector store** | Exact episode lookup |
| 500+ memories, latency matters | **PExM** | Constant-time generation (118ms vs 797ms) |
| Fewer than 50 memories | **Vector store** | PExM needs ~50 experiences to learn |
| Contradictory information over time | **PExM** | Natural forgetting vs stale entries |
| Multi-agent, need exact audit trail | **Vector store** | PExM has no discrete records |

---

## How It Works

### Architecture

```
+---------------------------------------------------------+
|                   Experience Model                       |
|                                                         |
|  +---------------------------------------------------+  |
|  |  Frozen Backbone (ModernBERT-base, 149M)          |  |
|  |  Encodes text into embeddings. Never updated.     |  |
|  +-------------------------+-------------------------+  |
|                            |                            |
|  +-------------------------v-------------------------+  |
|  |  Multi-Timescale Streams (4.7M trainable)         |  |
|  |                                                   |  |
|  |  fast   (lr=1e-3)  session-level patterns         |  |
|  |  medium (lr=1e-4)  project-level knowledge        |  |
|  |  slow   (lr=1e-5)  cross-project patterns         |  |
|  |                                                   |  |
|  |  Tiers emerge from learning rates, not design.    |  |
|  +--------+----------------+----------------+--------+  |
|           |                |                |           |
|    +------v------+  +------v------+  +------v------+   |
|    | Prediction  |  |  Context    |  |  Surprise   |   |
|    | Head        |  |  Generator  |  |  Gate       |   |
|    |             |  |             |  |             |   |
|    | Predicts    |  | Synthesizes |  | Modulates   |   |
|    | next state  |  | relevant    |  | update size |   |
|    |             |  | context     |  | by surprise |   |
|    +-------------+  +-------------+  +-------------+   |
+---------------------------------------------------------+
```

### Absorb: Experiencing Is Remembering

When an agent has an experience `(state, outcome)`:

1. The model predicts what outcome it expects
2. The actual outcome is compared to the prediction
3. Prediction error drives a gated weight update:
   - **High surprise** (novel experience) -> large update -> absorbed quickly
   - **Low surprise** (known pattern) -> tiny update -> weights barely change
   - **Contradiction** (stale knowledge) -> large error -> old weights overwritten

```python
metrics = model.absorb(
    state="debugging the auth module",
    outcome="JWT tokens expire after 3600s, refresh tokens in Redis with 7-day TTL"
)
print(metrics["z_surprise"])  # 0.72 -- novel, large update applied
```

### Generate: Retrieval Is Synthesis

When an agent needs context, a forward pass synthesizes across everything absorbed:

```python
result = model.generate("fixing the auth token expiry issue in tests")
# result["context_embedding"]  -- synthesized context from ALL absorbed experiences
# result["confidence"]         -- internal consistency score
# result["latency_ms"]         -- ~118ms, constant regardless of memory size
```

This is not retrieval. No single stored memory contains the answer. The model synthesizes across JWT knowledge, test failure patterns, and auth changes — all encoded in weights.

### Surprise: Novelty Without a Classifier

Instead of a "should I store this?" classifier, PExM uses prediction error z-scores:

```python
known = model.surprise_z("reading auth.py", "JWT with RS256, 3600s expiry")  # -> 0.38
novel = model.surprise_z("checking Spark cluster", "Shuffle spill at 15GB")  # -> 0.62
```

No classifier needed. Known experiences have low prediction error relative to the running distribution. Novel ones are outliers.

---

## Quickstart

### Install

```bash
git clone https://github.com/nikghodki/pexm.git
cd pexm
pip install torch transformers safetensors numpy
```

Requires Python 3.9+ and PyTorch with MPS (Apple Silicon) or CUDA (NVIDIA GPU).

### Basic Usage

```python
from pexm.core import ExperienceModel

# Load -- downloads ModernBERT-base on first run (~600MB)
model = ExperienceModel(device="mps")  # or "cuda:0"
optimizer = model.get_optimizer()
optimizer.zero_grad()

# Absorb experiences
experiences = [
    ("reading the auth module", "Uses JWT with RS256. Tokens expire after 3600s."),
    ("debugging login failure", "Email validator rejects plus signs. Fix in validators.py:42."),
    ("running tests after auth changes", "3 tests failed -- token expiry mid-suite."),
]

for state, outcome in experiences:
    model.absorb(state, outcome)
    model.maybe_optimizer_step(optimizer)
optimizer.step()
optimizer.zero_grad()

# Generate context for a new situation
result = model.generate("fixing auth token issues in the test suite")
print(f"Confidence: {result['confidence']:.3f}")
print(f"Latency: {result['latency_ms']:.0f}ms")

# Check if something is novel
known = model.surprise_z("reading the auth module", "JWT with RS256, 3600s expiry")
novel = model.surprise_z("setting up GraphQL federation", "Apollo Router with 4 subgraphs")
print(f"Known surprise: {known:.3f}")  # low
print(f"Novel surprise: {novel:.3f}")  # high
```

### Run the Benchmarks

```bash
# Generate 500 synthetic experiences
PYTHONPATH=. python pexm/benchmarks/generate_corpus.py

# Full benchmark suite (scaling + conversational + latency)
PYTHONPATH=. python pexm/benchmarks/run_full_benchmark.py
```

### Run the Examples

```bash
# Quick intro: absorb, generate, surprise, forgetting
PYTHONPATH=. python examples/quickstart.py

# Head-to-head comparison vs vector store
PYTHONPATH=. python examples/compare_vector_store.py
```

---

## Design Principles

**No memory objects.** There are no records to store, index, retrieve, evict, promote, merge, or expire. The model's weights are the only persistent state.

**Surprise controls learning.** Novel experiences update weights more than familiar ones. Automatic — no "importance" scoring needed.

**Tiers emerge, not designed.** Three adaptation streams at different learning rates. Fast-changing session patterns live in the fast stream. Stable knowledge accumulates in the slow stream. Analogous to L1/L2/L3 tiers, but continuous, not discrete.

**Constant-time generation.** A forward pass takes the same time whether the model has absorbed 10 or 10,000 experiences. Vector stores scale linearly.

**Forgetting is natural.** When new experiences contradict old ones, weight interference displaces the outdated knowledge. No staleness detection, no manual invalidation.

---

## Limitations

- **Not for exact recall.** PExM synthesizes across experiences. If you need verbatim lookup of a specific memory, use a vector store (see conversational memory benchmark above).
- **Needs ~50 experiences.** Below that, PExM underperforms vector retrieval. The model needs sufficient data to learn meaningful patterns.
- **Context is embeddings, not text.** The model generates context as embedding vectors, not readable text. Use the decoder module for approximate text recovery.
- **Absorb latency is ~270ms.** Includes backward pass and optimizer step. Use write-behind buffering for inline use.
- **Tested at 500 experiences.** Stream norms show no saturation at 1,500 absorptions, but 5K+ is unvalidated.
- **Single-agent only.** No multi-agent memory sharing or access control.

---

## Project Structure

```
pexm/
  core/
    experience_model.py   # ExperienceModel -- absorb, generate, surprise
    streams.py            # Multi-timescale adaptation streams
    decoder.py            # Embedding-to-text decoder (experimental)
  benchmarks/
    generate_corpus.py    # Synthetic experience generator (500+)
    run_benchmark.py      # Quick evaluation
    run_full_benchmark.py # Full benchmark suite (scaling + conversational + latency)
  data/                   # Generated corpora and results
  tests/
examples/
  quickstart.py           # 5-minute intro
  compare_vector_store.py # Head-to-head vs cosine retrieval
```

---

## Citation

```bibtex
@misc{pexm2026,
  title={PExM: Predictive Experience Models for AI Agent Memory},
  year={2026},
  howpublished={\url{https://github.com/nikghodki/pexm}},
}
```

---

## License

Apache-2.0
