# ContextOS Architecture

This document explains how the pieces fit together and where to look when you
want to extend the system. For the crate-by-crate map, see the
[README](../README.md).

## Data flow

```
  Agent / LLM
      │  gRPC (tonic)
      ▼
┌─────────────────────────────────────────────────────────────┐
│  contextos-server  (crates/server)                            │
│                                                              │
│   memory_svc ─┐                                              │
│   indexer_svc ─┤   Each service is a thin tonic adapter that │
│   policy_svc ──┤   converts proto ⇄ domain and delegates to   │
│   context_svc ─┤   a domain crate. The `conv` module handles  │
│   bus_svc ─────┤   UUID + timestamp marshalling.              │
│   optimizer_svc─┘                                              │
└───────────────┬──────────────────────────────────────────────┘
                │ in-process (Arc<MemoryKernel>)
                ▼
        ┌───────────────┐     ┌─────────────┐   ┌──────────────┐
        │  memory kernel │◄───►│  policy     │   │  memory bus  │
        │  (L1–L4 +     │     │  engine +   │   │  (broadcast) │
        │   RocksDB)    │     │  audit log  │   │              │
        └───────┬───────┘     └─────────────┘   └──────────────┘
                │
        ┌───────┴───────┬───────────────┐
        ▼               ▼               ▼
  ┌─────────────┐ ┌──────────────┐ ┌──────────────┐
  │  indexer    │ │     graph    │ │  optimizer   │
  │  (tree-     │ │  (petgraph,  │ │  (predictor  │
  │   sitter +  │ │   scopes)    │ │   + compress)│
  │   git2)     │ │              │ │              │
  └─────────────┘ └──────────────┘ └──────────────┘
```

## The memory kernel

The kernel (`crates/kernel`) owns all persisted memory. It is the only crate
that touches storage.

- **Tiers** (`src/memory/l1_session.rs` … `l4_archive.rs`): each tier is an
  isolated implementation behind a shared trait. L1 is an in-process map with
  TTL; L2–L4 are RocksDB column families, with L4 storing `zstd`-compressed
  payloads.
- **Storage** (`src/storage/`): a `Store` trait abstracts the backend
  (RocksDB today). Swap the backend by implementing `Store` — the rest of the
  kernel is backend-agnostic.
- **Scoring** (`src/scoring/`): recency / access-frequency scoring that feeds
  retrieval ranking and eviction.
- **Retrieval** (`src/retrieval/`): combines tier lookup with scoring to
  produce ranked results for `SearchMemory`.

## The indexer

`crates/indexer` builds a code symbol graph.

- **AST** (`src/ast/`): tree-sitter parses per-language; `parser.rs` is where
  new languages are registered.
- **Symbols** (`src/symbols/graph.rs`): the in-memory symbol graph and
  caller/callee edges.
- **Git** (`src/git/tracker.rs`): `git2`-based commit tracking. It computes
  per-function deltas (`FunctionDeltas`) and links them to test files.

## The policy engine

`crates/policy` enforces RBAC and keeps an append-only audit log.

- **RBAC** (`src/rbac.rs`): glob-pattern resource rules (e.g. `memory:*`) with
  per-action `ALLOW`/`DENY` effects and numeric priority.
- **Audit** (`src/audit.rs`): an in-memory, monotonically-ordered log of
  every permission decision. Swap in a durable backend (e.g. the RocksDB
  store) by replacing the backing collection.

## The memory bus

`crates/bus` is a pub/sub channel. Today it is a `tokio::sync::broadcast`
channel; the Kafka bridge is a documented production swap point. Publishing
with no active subscribers is a no-op (not an error), so producers never need
a live consumer to succeed.

## The context scheduler

`crates/scheduler` builds a token-budgeted window of context for a session.
- **Packer** (`src/packer.rs`): selects entries under a token budget.
- **Eviction** (`src/eviction.rs`): LRU / score / FIFO / hybrid policies.

## Optimizer & CRDT

- `crates/optimizer` — access-pattern `predictor.rs` (promotion scheduling)
  and `compressor.rs` (zstd now; LLM summarization is a hook).
- `crates/crdt` — `lww.rs` (last-writer-wins register) and `orset.rs`
  (observed-remove set) for conflict-free multi-region merge.

## Concurrency model

The server is a single `#[tokio::main]` runtime. All services share an
`Arc<MemoryKernel>`. The memory bus and policy audit log use interior
mutability; gRPC handlers are `async` and never hold locks across `await`
points.

## Testing strategy

- **Unit tests** live beside each crate (`#[cfg(test)]`), covering kernel
  tiers, scoring, RBAC, audit, packer, eviction, and CRDT merge semantics.
- **Integration tests** (`tests/integration`) spawn the real `contextos-server`
  binary on a random port and exercise every RPC end-to-end. They require a
  prior `cargo build` because they launch the compiled binary.
- **Python SDK tests** (`sdk/python/tests`) cover the data types and the
  client surface without needing a server.
