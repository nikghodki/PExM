# ContextOS Agent Runner - Quick Start Guide

## 30-Second Start

```bash
# 1. Check if ContextOS is running
./run_contextos_agent.py --check-services

# 2. If not running, start it
./run_contextos_agent.py --start-services

# 3. Run the demo
./run_contextos_agent.py --demo
```

## 5 Essential Commands

### 1. Check Services
```bash
./run_contextos_agent.py --check-services
# ✅ Shows if ContextOS is running
```

### 2. Start Services
```bash
./run_contextos_agent.py --start-services
# 🚀 Starts ContextOS with Docker
```

### 3. Store a Memory
```bash
./run_contextos_agent.py --store "Your memory text here"
# 💾 Stores text in agent memory
```

### 4. Search Memories
```bash
./run_contextos_agent.py --search "your query"
# 🔍 Semantic search across all memories
```

### 5. Interactive Mode
```bash
./run_contextos_agent.py --interactive
# 🎮 Opens interactive console
```

## Interactive Console Commands

Once in interactive mode (`./run_contextos_agent.py --interactive`):

```
store <text>        Store a new memory
search <query>      Search for memories
get <id>            Get memory by ID
index <path>        Index a code repository
symbols <query>     Search code symbols
status              Show connection info
help                Show help
exit                Exit console
```

## Common Workflows

### Workflow 1: Store and Search Knowledge
```bash
# Store some knowledge
./run_contextos_agent.py --store "Python uses indentation for blocks"
./run_contextos_agent.py --store "Rust is memory-safe without garbage collection"

# Search for it
./run_contextos_agent.py --search "memory safety"
```

### Workflow 2: Index and Query Code
```bash
# Start interactive mode
./run_contextos_agent.py --interactive

# Then in the console:
> index /path/to/your/project
> symbols ContextOSClient
> symbols memory
```

### Workflow 3: Agent Integration
```python
#!/usr/bin/env python3
from pathlib import Path
from run_contextos_agent import ContextOSAgent
from contextos import MemoryTier, Scope

# Create agent
agent = ContextOSAgent(agent_id="my-agent")
agent.connect()

# Store memory
agent.store_memory(
    "Found a bug in authentication.py line 42",
    tier=MemoryTier.L2_TASK,
    tags=["bug", "auth"]
)

# Search memories
results = agent.search_memory("authentication bugs", top_k=5)

# Cleanup
agent.disconnect()
```

## Configuration

### Custom Server
```bash
./run_contextos_agent.py --address "localhost:50051" --demo
```

### Custom Agent ID
```bash
./run_contextos_agent.py --agent-id "my-custom-agent" --demo
```

### Custom Workspace
```bash
./run_contextos_agent.py --workspace /path/to/workspace --demo
```

## Troubleshooting

**Problem**: Services not running
```bash
./run_contextos_agent.py --start-services
```

**Problem**: Connection refused
```bash
# Check Docker containers
docker ps

# Or check if port is in use
lsof -i :50051
```

**Problem**: Import errors
```bash
# Add SDK to Python path
export PYTHONPATH="/path/to/contextos/sdk/python:$PYTHONPATH"
```

## Next Steps

1. ✅ Run demo: `./run_contextos_agent.py --demo`
2. 📚 Read full docs: `AGENT_RUNNER_README.md`
3. 🔧 Try interactive mode: `./run_contextos_agent.py --interactive`
4. 🌟 Build your agent using the examples

## Get Help

```bash
./run_contextos_agent.py --help
```

For detailed documentation, see [AGENT_RUNNER_README.md](AGENT_RUNNER_README.md)
