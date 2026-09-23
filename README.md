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

## Results

Benchmarked on 500 synthetic coding experiences across 6 domains (auth, database, infrastructure, API, security, monitoring), with 50 held-out novel experiences and 8 test queries.

### Context Quality

| Method | Similarity to ideal context | Queries won |
|---|---|---|
| No memory | 0.730 | 0/8 |
| Vector store (top-5 cosine) | 0.937 | 0/8 |
| **PExM** | **0.979** | **8/8** |

PExM produces context +0.042 closer to the ideal than vector retrieval on every query. The gap widens at scale because vector retrieval slows linearly while PExM generation time is constant.

### Latency at 500 Memories

| Operation | PExM | Vector Store |
|---|---|---|
| Generate / Retrieve | **129ms** | 792ms |
| Absorb / Store | 269ms | <1ms |

Vector store writes are instant but reads get expensive. PExM writes are slower (online weight update) but reads are constant-time regardless of how much has been absorbed.

### Surprise Calibration

PExM tracks prediction error statistics to distinguish known from novel experiences:

| Category | Surprise score | Description |
|---|---|---|
| Known experiences | 0.422 | Low — model has absorbed this |
| Novel experiences | 0.479 | Higher — never seen before |
| Shuffled pairs | 0.442 | Middle — parts familiar, combination new |

Separation improves with scale: +0.034 at 100 experiences, +0.096 at 500.

### Natural Forgetting

When contradictory information is absorbed (e.g., "auth rewritten from JWT to OAuth2"):
- Old knowledge context similarity fades
- New knowledge becomes immediately dominant
- Old knowledge surprise increases (model finds stale info surprising)

No explicit eviction or staleness detection — contradictions resolve naturally.

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
# result["latency_ms"]         -- ~129ms, constant regardless of memory size
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

### Run the Benchmark

```bash
# Generate 500 synthetic experiences
python -m pexm.benchmarks.generate_corpus

# Run the full evaluation
python -m pexm.benchmarks.run_benchmark
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

- **Context is embeddings, not text.** The model generates context as embedding vectors, not readable text. Use the decoder module for approximate text recovery.
- **Absorb latency is ~270ms.** Includes backward pass and optimizer step. Use write-behind buffering for inline use.
- **Surprise calibration needs ~100 experiences.** Below that, running statistics lack sufficient data.
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
    run_benchmark.py      # Full evaluation suite
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
