# ContextOS Examples

Two runnable examples that show how to integrate ContextOS into an agent.
Both live in this directory and use no hardcoded paths — they locate the SDK
relative to the repo root.

## `agent_with_contextos.py`

A self-contained end-to-end demo of the **Python SDK** that exercises every
subsystem (memory, indexer, policy, context scheduler, bus). It requires no
external AI SDK — the "agent" is plain Python calling the client.

```bash
# 1. Start the server
cargo run --bin contextos-server

# 2. Install the SDK
cd sdk/python && pip install -e . && cd ../..

# 3. Run the demo
python3 examples/agent_with_contextos.py
```

If the server is not running, the example exits with a clear message.

## `claude_orchestrator.py`

A task-classifying orchestrator built on the **Claude Agent SDK** that routes
a task to a specialized agent (coding / debugging / research / documentation)
and uses ContextOS for persistent memory.

It degrades gracefully:

- **Without the Claude Agent SDK installed** (or without API access), the
  classification and agent-selection logic still run, but LLM responses use a
  local fallback rather than a real model call.
- **Without a running ContextOS server**, memory integration is skipped and
  the rest still works.

```bash
# Requires the SDK + Anthropic API access for real model responses:
pip install claude-agent-sdk

python3 examples/claude_orchestrator.py "Write a Python function to add two numbers"
python3 examples/claude_orchestrator.py --interactive
```

Options:

```bash
python3 claude_orchestrator.py --help
python3 claude_orchestrator.py --no-memory "Task"   # skip ContextOS memory
```

## Notes

- These examples are demonstrations, not part of the library's public API.
- The orchestrator's fallback mode means it can run in environments without
  API credits; wire in real model calls by installing `claude-agent-sdk` and
  configuring Anthropic access.
