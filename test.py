"""
Quick smoke test for the ContextOS Python SDK.
Run with the server already started:

    cargo run --bin contextos-server &
    python test.py
"""

from contextos import ContextOSClient, MemoryTier, Scope

client = ContextOSClient("localhost:50051")

# agent_id can be any string — the SDK maps it to a deterministic UUID
AGENT = "agent-001"

# ── Store ─────────────────────────────────────────────────────────────────────
entry_id = client.memory.store(
    agent_id=AGENT,
    content="refactored payment service to use async handlers",
    tier=MemoryTier.L2_TASK,
    scope=Scope.TEAM,
    tags=["payment", "async"],
)
print(f"Stored:  {entry_id}")

# ── Get ───────────────────────────────────────────────────────────────────────
entry = client.memory.get(entry_id)
print(f"Content: {entry.content}")
print(f"Tier:    {entry.tier}")
print(f"Score:   {entry.score:.2f}")

# ── Store a second entry for search ──────────────────────────────────────────
client.memory.store(
    agent_id=AGENT,
    content="auth middleware now validates JWT on every request",
    tier=MemoryTier.L2_TASK,
    scope=Scope.TEAM,
    tags=["auth", "jwt"],
)

# ── Search ────────────────────────────────────────────────────────────────────
results = client.memory.search(
    agent_id=AGENT,
    query="payment service changes",
    top_k=5,
)
print(f"\nSearch results ({len(results)} found):")
for r in results:
    print(f"  [{r.score:.2f}] {r.content[:80]}")

client.close()
print("\nAll done.")
