# Integrations

PExM connects to agent frameworks via two interfaces:

1. **MCP Server** — for Claude Code, OpenClaw, Codex, and any MCP-compatible agent
2. **HTTP API** — for everything else (Hermes, CrewAI, LangGraph, custom agents)

## Claude Code

Add to `.claude/settings.json`:

```json
{
  "mcpServers": {
    "pexm": {
      "command": "python",
      "args": ["-m", "pexm.serve.mcp_server"],
      "cwd": "/path/to/pexm"
    }
  }
}
```

Claude Code will see three tools: `pexm_absorb`, `pexm_query`, `pexm_surprise`.

## OpenClaw

Add to `.openclaw/config/mcp.json`:

```json
{
  "servers": {
    "pexm": {
      "command": "python",
      "args": ["-m", "pexm.serve.mcp_server"],
      "cwd": "/path/to/pexm"
    }
  }
}
```

## Codex

Add to your Codex agent config:

```json
{
  "mcp_servers": [{
    "name": "pexm",
    "command": "python -m pexm.serve.mcp_server",
    "working_directory": "/path/to/pexm"
  }]
}
```

## HTTP API (any framework)

Start the server:

```bash
PYTHONPATH=. python -m pexm.serve.http_server --port 7437
```

Then call from any language:

```python
import requests

# Absorb
requests.post("http://localhost:7437/absorb", json={
    "state": "debugging the auth module",
    "outcome": "JWT tokens expire after 3600 seconds"
})

# Query
r = requests.post("http://localhost:7437/query", json={
    "state": "fixing token expiry in tests",
    "top_k": 5
})
print(r.json()["context"])

# Surprise
r = requests.post("http://localhost:7437/surprise", json={
    "state": "checking k8s operator",
    "outcome": "CRD reconciliation every 30s"
})
print(r.json()["is_novel"])
```

## CrewAI

Use the HTTP API as a custom tool:

```python
from crewai import Agent, Tool
import requests

PEXM_URL = "http://localhost:7437"

def pexm_query(state: str) -> str:
    r = requests.post(f"{PEXM_URL}/query", json={"state": state, "top_k": 5})
    return r.json()["context"]

def pexm_absorb(state: str, outcome: str) -> str:
    r = requests.post(f"{PEXM_URL}/absorb", json={"state": state, "outcome": outcome})
    return f"Absorbed. Surprise: {r.json()['surprise']:.3f}"

memory_tool = Tool(name="memory_query", func=pexm_query,
                   description="Query PExM for relevant context about the current task")
learn_tool = Tool(name="memory_learn", func=pexm_absorb,
                  description="Store a new learning in PExM memory")

agent = Agent(role="developer", tools=[memory_tool, learn_tool])
```

## LangGraph

```python
from langgraph.prebuilt import ToolNode
import requests

PEXM_URL = "http://localhost:7437"

def pexm_query(state: str, top_k: int = 5) -> str:
    """Query PExM for relevant context."""
    r = requests.post(f"{PEXM_URL}/query", json={"state": state, "top_k": top_k})
    return r.json()["context"]

def pexm_absorb(state: str, outcome: str) -> str:
    """Absorb a new experience into PExM."""
    r = requests.post(f"{PEXM_URL}/absorb", json={"state": state, "outcome": outcome})
    return f"Surprise: {r.json()['surprise']:.3f}"

tool_node = ToolNode([pexm_query, pexm_absorb])
```

## Hermes / Custom Agents

Any agent that can make HTTP POST requests can use PExM. The pattern is:

1. Start PExM: `PYTHONPATH=. python -m pexm.serve.http_server`
2. After each agent action: `POST /absorb` with what happened
3. Before each decision: `POST /query` with current task
4. Optionally: `POST /surprise` to check if a result is worth absorbing
