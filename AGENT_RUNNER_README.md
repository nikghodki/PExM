# ContextOS Agent Runner

A comprehensive Python script for running and interacting with ContextOS from an AI agent.

## Overview

The `run_contextos_agent.py` script provides a complete interface for:
- **Service Management**: Check, start, and manage ContextOS services
- **Memory Operations**: Store, search, and retrieve agent memories
- **Code Indexing**: Index repositories and search for symbols
- **Interactive Mode**: REPL-style console for exploring ContextOS
- **Demo Mode**: Automated demonstration of all features

## Quick Start

### 1. Check if Services are Running

```bash
./run_contextos_agent.py --check-services
```

### 2. Start ContextOS Services

```bash
# Using Docker (recommended)
./run_contextos_agent.py --start-services

# Using cargo (requires Rust)
./run_contextos_agent.py --start-services --no-docker
```

### 3. Run Demo Mode

```bash
./run_contextos_agent.py --demo
```

This will demonstrate:
- Storing memories with different tiers (L1-L4)
- Semantic search across memories
- Retrieving specific memories by ID
- Indexing code repositories
- Searching for code symbols

### 4. Interactive Console

```bash
./run_contextos_agent.py --interactive
```

Available commands in interactive mode:
- `store <text>` - Store a memory
- `search <query>` - Search memories
- `get <id>` - Get memory by ID
- `index <path>` - Index a repository
- `symbols <query>` - Search code symbols
- `status` - Show connection status
- `help` - Show available commands
- `exit` - Exit console

## Command Line Operations

### Store a Memory

```bash
./run_contextos_agent.py --store "Python is a high-level programming language"
```

### Search Memories

```bash
./run_contextos_agent.py --search "programming language"
```

### Index a Repository

```bash
./run_contextos_agent.py --index /path/to/your/repo
```

## Configuration Options

### Connection

```bash
# Custom server address
./run_contextos_agent.py --address "remote-server:50051" --demo

# Custom agent ID
./run_contextos_agent.py --agent-id "my-agent-001" --demo

# Custom workspace
./run_contextos_agent.py --workspace /path/to/workspace --demo
```

## Architecture

### ContextOSAgent Class

The main `ContextOSAgent` class provides:

1. **Service Management**
   - `check_services()`: Health check for ContextOS services
   - `start_services()`: Automated service startup

2. **Connection Management**
   - `connect()`: Establish connection to ContextOS
   - `disconnect()`: Clean disconnection

3. **Memory Operations**
   - `store_memory()`: Store memories with tier, scope, and tags
   - `search_memory()`: Semantic search across memories
   - `get_memory()`: Retrieve specific memory by ID

4. **Indexing Operations**
   - `index_repository()`: AST-based code indexing
   - `search_symbols()`: Query indexed symbols

5. **Demo & Interactive Modes**
   - `run_demo()`: Automated feature demonstration
   - `run_interactive()`: Interactive console

## Memory Tiers

ContextOS uses a 4-tier memory hierarchy:

- **L1_SESSION**: Short-term session memory
- **L2_TASK**: Task-specific memory
- **L3_SEMANTIC**: Long-term semantic memory
- **L4_ARCHIVE**: Archive/historical memory

Example:
```python
agent.store_memory(
    content="Important fact",
    tier=MemoryTier.L2_TASK,
    scope=Scope.PRIVATE,
    tags=["important", "fact"]
)
```

## Memory Scopes

Control visibility of memories:

- **PRIVATE**: Only this agent
- **TEAM**: Shared with team
- **ORG**: Organization-wide
- **EPHEMERAL**: Temporary

## Code Indexing

Index repositories for symbol-level search:

```bash
# Index with specific languages
./run_contextos_agent.py --index /path/to/repo

# Then search for symbols
./run_contextos_agent.py --interactive
> symbols ContextOSClient
```

Supported languages:
- Python
- Rust
- JavaScript
- TypeScript
- Go
- Java
- C/C++

## Integration with Claude Agent SDK

The script can be integrated with the Claude Agent SDK for autonomous agent operations:

```python
import asyncio
from run_contextos_agent import ContextOSAgent

async def autonomous_agent():
    agent = ContextOSAgent(agent_id="claude-agent-001")

    if not agent.connect():
        agent.start_services()
        agent.connect()

    # Store agent thoughts
    agent.store_memory(
        "Analyzing codebase for optimization opportunities",
        tier=MemoryTier.L2_TASK
    )

    # Search previous insights
    results = agent.search_memory("optimization", top_k=5)

    # Index current workspace
    agent.index_repository(Path.cwd())

    agent.disconnect()

asyncio.run(autonomous_agent())
```

## Troubleshooting

### Services Not Running

```bash
# Check status
./run_contextos_agent.py --check-services

# Start services
./run_contextos_agent.py --start-services
```

### Connection Errors

1. Verify ContextOS server is running: `docker ps` or `cargo build --release`
2. Check port availability: `lsof -i :50051`
3. Verify network connectivity
4. Check firewall settings

### Import Errors

```bash
# Ensure ContextOS SDK is in Python path
export PYTHONPATH="/path/to/contextos/sdk/python:$PYTHONPATH"

# Or install as package
cd contextos/sdk/python
pip install -e .
```

## Examples

### Example 1: Knowledge Base Agent

```python
# Store domain knowledge
agent.store_memory(
    "REST APIs use HTTP methods: GET, POST, PUT, DELETE",
    tier=MemoryTier.L3_SEMANTIC,
    tags=["api", "http", "web"]
)

# Later retrieve it
results = agent.search_memory("HTTP methods", top_k=1)
```

### Example 2: Code Analysis Agent

```python
# Index codebase
agent.index_repository(
    repo_path=Path("/project"),
    languages=["python", "javascript"]
)

# Find specific functions
symbols = agent.search_symbols("authentication", top_k=10)
```

### Example 3: Multi-Agent Memory Sharing

```python
# Agent 1: Store team knowledge
agent1 = ContextOSAgent(agent_id="agent-1")
agent1.connect()
agent1.store_memory(
    "Database connection string is in .env file",
    tier=MemoryTier.L2_TASK,
    scope=Scope.TEAM  # Share with team
)

# Agent 2: Access shared knowledge
agent2 = ContextOSAgent(agent_id="agent-2")
agent2.connect()
results = agent2.search_memory("database connection", scope=Scope.TEAM)
```

## Performance Tips

1. **Use Appropriate Tiers**: Store session data in L1, long-term knowledge in L3
2. **Tag Effectively**: Use descriptive tags for better organization
3. **Incremental Indexing**: Use `incremental=True` for large repos
4. **Batch Operations**: Store multiple memories together when possible
5. **Scope Wisely**: Use PRIVATE for agent-specific, TEAM for shared knowledge

## Requirements

- Python 3.8+
- ContextOS services (Docker or Rust)
- ContextOS Python SDK
- grpcio

## Files

- `run_contextos_agent.py` - Main agent runner script
- `contextos/sdk/python/` - Python SDK
- `docker-compose.yml` - Service orchestration
- `proto/` - gRPC protocol definitions

## See Also

- [ContextOS README](README.md) - Full system documentation
- [Claude Agent SDK](https://github.com/anthropics/claude-agent-sdk) - Agent framework
- [examples/claude_orchestrator.py](examples/claude_orchestrator.py) - Agent orchestration example

## License

Same as ContextOS project.
