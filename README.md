# ContextOS

**Enterprise AI Memory Backbone** — a distributed, model-agnostic memory operating system for AI agents and multi-agent systems.

ContextOS sits between AI agents and enterprise data systems to provide scalable, safe, and high-performance memory orchestration. It keeps agents grounded in your codebase, reduces hallucinations, cuts token usage, and gives every memory operation a full audit trail.

**Documentation:** [Architecture](docs/ARCHITECTURE.md) · [Python SDK](docs/SDK.md) · [Deployment](docs/DEPLOYMENT.md) · [Contributing](CONTRIBUTING.md) · [Code of Conduct](CODE_OF_CONDUCT.md)

---

## Why ContextOS

| Problem today | ContextOS solution |
|---|---|
| AI agents are stateless or ephemeral | Persistent tiered memory (L1–L4) backed by RocksDB |
| Naive vector retrieval misses code context | AST-indexed symbol graph via tree-sitter |
| No Git awareness | Commit-level diff tracking and function-delta linking |
| No memory sharing between agents | Multi-agent memory graph with scope-based visibility |
| No access control | RBAC policy engine with immutable audit log |
| High token waste | Token-aware context packing and compression |
| No observability | Prometheus metrics, Grafana dashboard, Jaeger tracing |

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        AI Agents / SDKs                         │
└────────────────────────────┬────────────────────────────────────┘
                             │ gRPC
┌────────────────────────────▼────────────────────────────────────┐
│                      ContextOS Server                           │
│                                                                 │
│  ┌──────────────┐  ┌──────────────┐  ┌───────────────────────┐ │
│  │    Memory    │  │   Indexer    │  │   Context Scheduler   │ │
│  │   Service    │  │   Service    │  │       Service         │ │
│  └──────┬───────┘  └──────┬───────┘  └───────────┬───────────┘ │
│         │                 │                       │             │
│  ┌──────▼─────────────────▼───────────────────────▼──────────┐ │
│  │                      Memory Kernel                        │ │
│  │  L1 Session │ L2 Task │ L3 Semantic │ L4 Archive (zstd)  │ │
│  │                    [RocksDB]                              │ │
│  └───────────────────────────────────────────────────────────┘ │
│                                                                 │
│  ┌───────────────┐  ┌──────────────┐  ┌─────────────────────┐ │
│  │ Policy Engine │  │ Memory Graph │  │    Memory Bus       │ │
│  │  RBAC + Audit │  │ (petgraph)   │  │  (tokio broadcast)  │ │
│  └───────────────┘  └──────────────┘  └─────────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
```

### Crate Map

| Crate | Phase | Purpose |
|---|---|---|
| `contextos-kernel` | 1 | Tiered memory (L1–L4), RocksDB persistence, scoring, retrieval |
| `contextos-indexer` | 1 | tree-sitter AST parsing, symbol graph, git2 diff tracking |
| `contextos-graph` | 1 | Enterprise memory graph — typed nodes, edges, scope-filtered BFS |
| `contextos-policy` | 2 | RBAC with glob-pattern rules, append-only audit log |
| `contextos-scheduler` | 2 | Token-aware context packing, LRU/Score/FIFO/Hybrid eviction |
| `contextos-bus` | 2 | Pub/sub memory bus (tokio broadcast + Kafka bridge stub) |
| `contextos-optimizer` | 3 | Access-pattern predictor, zstd + LLM-summary compression |
| `contextos-crdt` | 3 | LWW register + OR-Set for conflict-free multi-region sync |
| `contextos-server` | — | gRPC server binary (Tonic) |
| `ctx` (CLI) | — | Terminal client for all subsystems |

### Memory Tiers

| Tier | Storage | TTL | Use case |
|---|---|---|---|
| L1 Session | In-process HashMap | Yes | Hot agent context, sub-ms access |
| L2 Task | RocksDB CF `l2_task` | No | Structured task memories, persisted |
| L3 Semantic | RocksDB CF `l3_semantic` | No | Embedding-indexed semantic memories |
| L4 Archive | RocksDB CF `l4_archive` (zstd) | No | Compressed long-term storage |

### Proto Services (6 total)

| Proto file | Service | Key operations |
|---|---|---|
| `memory.proto` | `MemoryService` | Store, Get, Search, Promote, Delete, List |
| `indexer.proto` | `IndexerService` | IndexRepo, QuerySymbols, GetCommitDiff, FunctionDeltas |
| `policy.proto` | `PolicyService` | CheckPermission, CreateRole, AssignRole, AuditLog |
| `context.proto` | `ContextSchedulerService` | ScheduleContext, GetWindow, Evict, CloseSession |
| `bus.proto` | `MemoryBusService` | Publish, Subscribe (server-streaming) |
| `optimizer.proto` | `OptimizerService` | PromotionSuggestions, TriggerCompression |

---

## Prerequisites

| Tool | Version | Install |
|---|---|---|
| Rust | stable ≥ 1.80 | `curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs \| sh` |
| protoc | ≥ 3.21 | `brew install protobuf` / `apt install protobuf-compiler` |
| Python | ≥ 3.10 | system or pyenv |
| Docker + Compose | any recent | docker.com |

---

## Getting Started

### 1. Clone and enter the project

```bash
git clone https://github.com/contextos/contextos.git
cd contextos
```

### 2. Install Rust (if not already installed)

```bash
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y
source "$HOME/.cargo/env"
```

### 3. Install protoc

```bash
# macOS
brew install protobuf

# Ubuntu / Debian
sudo apt-get install -y protobuf-compiler
```

### 4. Verify the build

```bash
cargo check        # type-check all crates (~2 min first run, cached after)
cargo build        # compile server + CLI binaries
```

### 5. Run tests

```bash
# Rust unit tests
cargo test --all

# Python SDK tests (no server required)
cd sdk/python
pip install -e ".[dev]"
python -m pytest tests/ -v
cd ../..
```

Expected output:
```
test result: ok. N passed; 0 failed    (Rust — unit + integration)
25 passed                               (Python)
```

### 6. Start the local stack (optional)

```bash
docker-compose up -d
```

This starts: Kafka · Zookeeper · Prometheus · Grafana · Jaeger

| Service | URL |
|---|---|
| Grafana dashboard | http://localhost:3000 (admin/admin) |
| Prometheus | http://localhost:9091 |
| Jaeger UI | http://localhost:16686 |
| Kafka | localhost:9092 |

### 7. Start the gRPC server

```bash
cargo run --bin contextos-server
```

```
INFO contextos_server: ContextOS server starting addr=[::1]:50051
INFO contextos_server: All subsystems initialised. Listening on [::1]:50051
```

Environment variables:

| Variable | Default | Description |
|---|---|---|
| `CONTEXTOS_BIND` | `[::1]:50051` | gRPC listen address |
| `CONTEXTOS_ROCKSDB_PATH` | `./contextos-data/rocksdb` | RocksDB data directory |
| `CONTEXTOS_LOG` | `info` | Log level (trace/debug/info/warn/error) |
| `KAFKA_BROKERS` | `kafka:9092` | Memory bus Kafka brokers |

### 8. Use the CLI

```bash
# Build the CLI
cargo build --bin ctx

# Store a memory
./target/debug/ctx mem store \
  --agent-id "$(uuidgen)" \
  --content "The auth middleware now validates JWT on every request." \
  --tier 2

# Index a repository
./target/debug/ctx index repo \
  --path ./  \
  --repo-id contextos \
  --lang rust

# Tail audit events
./target/debug/ctx audit tail --principal-id "$(uuidgen)"

# Show all subcommands
./target/debug/ctx --help
```

### 9. Use the Python SDK

```python
from contextos import ContextOSClient, MemoryTier, Scope

client = ContextOSClient("localhost:50051")

# agent_id can be any string — the SDK maps it to a deterministic UUID
AGENT = "agent-001"

# Store a memory
entry_id = client.memory.store(
    agent_id=AGENT,
    content="refactored payment service to use async handlers",
    tier=MemoryTier.L2_TASK,
    scope=Scope.TEAM,
    tags=["payment", "async"],
)
print(f"Stored: {entry_id}")

# Retrieve it
entry = client.memory.get(entry_id)
print(entry.content)

# Semantic search
results = client.memory.search(
    agent_id=AGENT,
    query="payment service changes",
    top_k=5,
)
for r in results:
    print(f"[{r.score:.2f}] {r.content[:80]}")

client.close()
```

The SDK exposes all six subsystems:

```python
client.memory    # store / get / search / promote / delete / list
client.indexer  # index_repo / query_symbols / get_symbol /
                # get_commit_diff / query_function_deltas
client.policy   # check_permission / create_role / assign_role /
                # list_audit_events / stream_audit_events
client.context  # schedule_context / get_window / evict / close_session
client.bus      # publish / subscribe (server-streaming)
client.optimizer# promotion_suggestions / trigger_compression
```

A runnable end-to-end example that exercises every subsystem is in
[examples/agent_with_contextos.py](examples/agent_with_contextos.py).

---

## Development

### Project structure

```
contextos/
├── Cargo.toml              # Rust workspace root
├── proto/                  # Protobuf service definitions (6 files)
├── crates/
│   ├── kernel/             # Memory kernel (L1–L4)
│   ├── indexer/            # Code indexer + git tracker
│   ├── graph/              # Enterprise memory graph
│   ├── policy/             # RBAC + audit log
│   ├── scheduler/          # Context scheduler
│   ├── bus/                # Memory event bus
│   ├── optimizer/          # Self-optimizing memory (Phase 3)
│   ├── crdt/               # CRDT sync primitives (Phase 3)
│   └── server/             # gRPC server binary
├── cli/                    # `ctx` terminal client
├── sdk/python/             # Python gRPC SDK
└── deploy/
    ├── k8s/                # Kubernetes manifests
    ├── helm/               # Helm chart
    └── observability/      # Prometheus / Grafana / Jaeger configs
```

### Common commands

```bash
make build          # cargo build --release
make check          # cargo check
make test           # cargo test --all
make fmt            # cargo fmt --all
make lint           # cargo clippy --all -- -D warnings
make proto-python   # regenerate Python gRPC stubs
make sdk            # pip install -e sdk/python/[dev]
make sdk-test       # run Python SDK tests
make docker-up      # start local infra stack
make docker-down    # stop and remove containers
```

### What is implemented today

All six gRPC services are wired into the server (`crates/server/src/main.rs`)
and are exercised by the integration test suite: `memory`, `indexer`,
`policy`, `context` (scheduler), `bus`, and `optimizer`. The Python SDK
exposes all of them under `client.memory`, `client.indexer`, `client.policy`,
`client.context`, `client.bus`, and `client.optimizer`.

Two features are intentional stubs awaiting your model/integration:

- **LLM-assisted compression** (`optimizer`): the plumbing and `zstd`
  compression are real; the summarization step is a hook you wire to a model.
- **Multi-region sync** (`crdt`): the LWW register and OR-Set primitives are
  implemented and tested, but a live multi-node deployment has not been
  exercised yet.

### Adding a new gRPC service

1. Add the `.proto` file to `proto/`.
2. Create a crate under `crates/your-service/` and add
   `tonic_build::compile_protos("../../proto/your-service.proto")` to its
   `build.rs`.
3. Implement the service trait in `crates/server/src/your_svc.rs`.
4. Register it in `crates/server/src/main.rs` with `.add_service(...)`.
5. Regenerate the Python stubs (`make proto-python`) and add a client under
   `sdk/python/contextos/client.py`.

```rust
// In crates/server/src/main.rs, after `cargo build` generates the stubs:
Server::builder()
    .add_service(health_svc)
    .add_service(MemoryServiceServer::new(memory_svc))   // ← add your service here
    .serve(addr)
    .await?;
```

---

## Roadmap

### Phase 1 — Foundation ✅
- [x] Rust memory kernel (L1–L4 tiered storage)
- [x] tree-sitter code indexer
- [x] Git diff / function-delta tracking
- [x] gRPC API server (all six services)
- [x] Python SDK

### Phase 2 — Multi-agent ✅
- [x] Enterprise memory graph (petgraph)
- [x] RBAC policy engine + audit log
- [x] Distributed memory bus (tokio broadcast / Kafka)
- [x] Token-aware context scheduler

### Phase 3 — Self-optimizing 🔶
- [x] Access-pattern predictor + promotion scheduling
- [ ] LLM-assisted compression — **stub, wire your model**
- [ ] CRDT-based multi-region sync — primitives done, **multi-node untested**
- [x] Kubernetes deploy manifests + Helm chart
- [x] Prometheus + Grafana + Jaeger observability

---

## Contributing

1. Fork the repository
2. Create a feature branch: `git checkout -b feat/your-feature`
3. Run `make fmt && make lint && make test` before committing
4. Open a pull request

---

## License

MIT OR Apache-2.0
