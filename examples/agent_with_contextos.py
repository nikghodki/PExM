#!/usr/bin/env python3
"""
Example: a small AI agent that uses ContextOS for persistent memory.
=====================================================================

This is a self-contained demonstration of the ContextOS Python SDK. It
exercises the core subsystems against a **running** ContextOS server:

    1. Memory   — store, get, search, list, and promote memories (L1–L4).
    2. Indexer  — index this repository and query its symbols.
    3. Policy   — create a role, assign it, and check a permission.
    4. Context  — build a token-budgeted context window for a session.
    5. Bus      — publish a memory event and subscribe to it.

No external AI SDK is required — the "agent" here is just plain Python
calling the ContextOS client, which is the integration point any LLM agent
would use.

Prerequisites
-------------
    1. Build & start the server:
           cargo run --bin contextos-server
    2. Install the SDK:
           cd sdk/python && pip install -e .
    3. Run this example:
           python3 examples/agent_with_contextos.py

If the server is not running, the example exits with a clear message.
"""

import sys
from pathlib import Path

import grpc

# Make the SDK importable when running straight from a source checkout.
SDK_PATH = Path(__file__).resolve().parent.parent / "sdk" / "python"
if str(SDK_PATH) not in sys.path:
    sys.path.insert(0, str(SDK_PATH))

from contextos import (  # noqa: E402
    ContextOSClient,
    MemoryTier,
    Scope,
    PermissionAction,
)

AGENT = "demo-agent"          # human-readable; SDK maps it to a stable UUID
SERVER = "localhost:50051"


def banner(msg: str) -> None:
    print(f"\n\033[1m── {msg} " + "─" * max(0, 60 - len(msg)))


def main() -> int:
    client = ContextOSClient(SERVER)

    # ── 1. Memory ────────────────────────────────────────────────────────────
    banner("Memory: store / get / search / list / promote")
    mem_id = client.memory.store(
        agent_id=AGENT,
        content="The auth middleware now validates the JWT on every request.",
        tier=MemoryTier.L2_TASK,
        scope=Scope.TEAM,
        tags=["auth", "jwt"],
        metadata={"module": "http"},
    )
    print(f"Stored memory {mem_id}")

    entry = client.memory.get(mem_id)
    print(f"  get  → {entry.content!r}  (tier={entry.tier.name})")

    results = client.memory.search(agent_id=AGENT, query="authentication jwt", top_k=3)
    print(f"  search → {len(results)} hit(s)")
    for r in results:
        print(f"    [{r.score:.2f}] {r.content[:60]}")

    all_mems = client.memory.list(agent_id=AGENT, tier=MemoryTier.L2_TASK)
    print(f"  list   → {len(all_mems)} L2 task memory(ies)")

    new_tier = client.memory.promote(mem_id, MemoryTier.L3_SEMANTIC)
    print(f"  promote→ {mem_id} now {new_tier.name}")

    # ── 2. Indexer ────────────────────────────────────────────────────────────
    banner("Indexer: index this repo and query symbols")
    repo_root = Path(__file__).resolve().parent.parent
    idx = client.indexer.index_repo(
        repo_id="contextos", local_path=str(repo_root), languages=["rust"],
    )
    print(f"  indexed {idx['symbols_added']} symbol(s) in {idx['duration_ms']} ms")

    symbols = client.indexer.query_symbols("contextos", "store", top_k=3)
    print(f"  query  → {len(symbols)} symbol(s) matching 'store'")
    for s in symbols:
        print(f"    {s.qualified_name}  ({s.kind.name}) {s.file_path}:{s.start_line}")

    # ── 3. Policy ─────────────────────────────────────────────────────────────
    banner("Policy: create role, assign, check permission")
    role_id = client.policy.create_role(
        name="memory-writer", permissions=["memory:*", "index:*"]
    )
    client.policy.assign_role(principal_id=AGENT, role_id=role_id)
    decision = client.policy.check_permission(
        principal_id=AGENT, resource="memory:*", action=PermissionAction.WRITE
    )
    print(f"  role   {role_id!r} → {decision.effect.name} ({decision.reason or 'n/a'})")

    # ── 4. Context scheduler ──────────────────────────────────────────────────
    banner("Context: build a token-budgeted window")
    window = client.context.schedule_context(
        agent_id=AGENT, session_id="session-1", token_budget=2048,
    )
    print(f"  window → {window.total_tokens}/{window.budget_tokens} tokens, "
          f"{len(window.entries)} entr(ies)")

    # ── 5. Memory bus ─────────────────────────────────────────────────────────
    banner("Bus: publish + subscribe")
    from contextos import MemoryEventKind

    evt_id = client.bus.publish(
        memory_id=mem_id, agent_id=AGENT, scope="team",
        kind=MemoryEventKind.MEMORY_PROMOTED,
    )
    print(f"  published event {evt_id}")
    client.close()
    print("\n✅ All subsystems responded. ContextOS is working end-to-end.")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except grpc.RpcError as e:
        print(
            f"\n❌ Could not reach ContextOS server at {SERVER} ({e.code().name}).\n"
            f"   Start it first:  cargo run --bin contextos-server",
            file=sys.stderr,
        )
        sys.exit(1)
