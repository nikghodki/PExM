# Python SDK

The Python SDK (`sdk/python`) is a thin, typed wrapper over the gRPC stubs.
It is the recommended integration path for agents and applications.

## Install

```bash
# From a source checkout (editable):
cd sdk/python
pip install -e ".[dev]"   # includes pytest, ruff, mypy

# Or from the published package once released:
pip install contextos
```

Requirements: Python ≥ 3.10, `grpcio`, `protobuf`.

## Quick start

```python
from contextos import ContextOSClient, MemoryTier, Scope

with ContextOSClient("localhost:50051") as client:
    AGENT = "agent-001"      # any string → deterministic UUID

    entry_id = client.memory.store(
        agent_id=AGENT,
        content="The auth middleware now validates the JWT on every request.",
        tier=MemoryTier.L2_TASK,
        scope=Scope.TEAM,
        tags=["auth"],
        metadata={"module": "http"},
    )

    entry = client.memory.get(entry_id)
    print(entry.content, entry.created_at)

    for r in client.memory.search(AGENT, "jwt validation", top_k=5):
        print(f"[{r.score:.2f}] {r.content}")
```

> **IDs:** the server stores UUIDs. The SDK accepts any string for
> `agent_id` / `principal_id` and maps it deterministically (UUIDv5), so the
> same human-readable string always resolves to the same UUID across calls.

## The six clients

| Client | Methods |
|---|---|
| `client.memory` | `store`, `get`, `search`, `promote`, `delete`, `list` |
| `client.indexer` | `index_repo`, `query_symbols`, `get_symbol`, `get_commit_diff`, `query_function_deltas` |
| `client.policy` | `check_permission`, `create_role`, `assign_role`, `list_audit_events`, `stream_audit_events` |
| `client.context` | `schedule_context`, `get_window`, `evict`, `close_session` |
| `client.bus` | `publish`, `subscribe` (server-streaming) |
| `client.optimizer` | `promotion_suggestions`, `trigger_compression` |

## Streaming

`client.bus.subscribe` and `client.policy.stream_audit_events` return a
server-streaming iterator. Consume it in a thread or an `asyncio` task:

```python
for event in client.bus.subscribe(agent_id="agent-001"):
    print(event.kind, event.payload)
```

## TLS

Pass `use_tls=True` to open a `grpc.secure_channel` (with default SSL
credentials). For a production deployment you will want to supply a CA and
server cert via `grpc.ssl_channel_credentials` — the SDK exposes the channel
constructor for that.

## Regenerating gRPC stubs

If you change a `.proto` file, regenerate the Python stubs:

```bash
make proto-python     # from the repo root
```

## Tests

```bash
cd sdk/python
ruff check .                      # lint
python -m pytest tests/ -v        # 25 tests, no server required
```
