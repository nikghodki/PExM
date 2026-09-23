#!/usr/bin/env python3
"""
Example: Claude Agent with ContextOS Integration
=================================================

This example demonstrates how to build a Claude agent that uses
ContextOS for persistent memory, code indexing, and knowledge management.

The agent can:
1. Store and retrieve memories across sessions
2. Search its knowledge base semantically
3. Index codebases and search for symbols
4. Share knowledge with other agents (team scope)

Usage:
    python3 agent_with_contextos.py "Analyze the authentication module"
"""

import asyncio
import sys
from pathlib import Path

# Add paths
CONTEXTOS_ROOT = Path(__file__).parent.parent
SDK_PATH = CONTEXTOS_ROOT / "sdk" / "python"
if str(SDK_PATH) not in sys.path:
    sys.path.insert(0, str(SDK_PATH))

# Add runner script to path
RUNNER_PATH = CONTEXTOS_ROOT
if str(RUNNER_PATH) not in sys.path:
    sys.path.insert(0, str(RUNNER_PATH))

try:
    from run_contextos_agent import ContextOSAgent
    from contextos import MemoryTier, Scope
    AGENT_AVAILABLE = True
except ImportError:
    print("❌ run_contextos_agent.py not found")
    AGENT_AVAILABLE = False

try:
    import claude_agent_sdk
    from claude_agent_sdk import query, ClaudeAgentOptions
    SDK_AVAILABLE = True
except ImportError:
    print("⚠️  Claude Agent SDK not available (optional for this example)")
    SDK_AVAILABLE = False


class SmartCodeAgent:
    """
    A smart coding agent that uses ContextOS for:
    - Persistent memory across sessions
    - Code indexing and symbol search
    - Knowledge sharing between agents
    """

    def __init__(self, agent_id: str, workspace: Path):
        self.agent_id = agent_id
        self.workspace = workspace
        self.contextos = ContextOSAgent(
            agent_id=agent_id,
            workspace=workspace
        )

        print(f"\n🤖 Smart Code Agent initialized")
        print(f"   Agent ID: {agent_id}")
        print(f"   Workspace: {workspace}")

    async def start(self):
        """Initialize the agent"""
        print("\n🚀 Starting agent...")

        # Check if ContextOS is running
        if not self.contextos.check_services():
            print("   ContextOS not running, attempting to start...")
            if not self.contextos.start_services():
                print("❌ Failed to start ContextOS services")
                return False

        # Connect
        if not self.contextos.connect():
            print("❌ Failed to connect to ContextOS")
            return False

        # Index workspace on startup
        print("   Indexing workspace...")
        self.contextos.index_repository(
            repo_path=self.workspace,
            repo_id=self.workspace.name,
            languages=["python", "rust", "javascript"],
            incremental=True
        )

        print("✅ Agent ready!")
        return True

    async def process_task(self, task: str) -> str:
        """Process a task with memory and context"""
        print(f"\n📋 Task: {task}")
        print("-" * 60)

        # 1. Store the task in memory
        print("💾 Storing task in memory...")
        self.contextos.store_memory(
            content=f"Task: {task}",
            tier=MemoryTier.L2_TASK,
            scope=Scope.PRIVATE,
            tags=["task", "active"]
        )

        # 2. Search for relevant previous knowledge
        print("🔍 Searching for relevant knowledge...")
        relevant_memories = self.contextos.search_memory(
            query=task,
            top_k=5,
            scope=None  # Search all scopes
        )

        # 3. Search for relevant code symbols
        print("🔍 Searching for relevant code symbols...")
        keywords = self._extract_keywords(task)
        relevant_symbols = []
        for keyword in keywords:
            symbols = self.contextos.search_symbols(
                query=keyword,
                repo_id=self.workspace.name,
                top_k=3
            )
            relevant_symbols.extend(symbols)

        # 4. Build context for the agent
        context = self._build_context(
            task=task,
            memories=relevant_memories,
            symbols=relevant_symbols
        )

        print(f"\n🧠 Context built:")
        print(f"   Relevant memories: {len(relevant_memories)}")
        print(f"   Relevant symbols: {len(relevant_symbols)}")

        # 5. If Claude SDK is available, use it
        if SDK_AVAILABLE:
            result = await self._process_with_claude(task, context)
        else:
            result = await self._process_locally(task, context)

        # 6. Store the result
        print("\n💾 Storing result in memory...")
        self.contextos.store_memory(
            content=f"Result for '{task}': {result[:200]}...",
            tier=MemoryTier.L3_SEMANTIC,
            scope=Scope.TEAM,  # Share with team
            tags=["result", "completed"]
        )

        return result

    def _extract_keywords(self, text: str) -> list[str]:
        """Extract important keywords from text"""
        # Simple keyword extraction (could be more sophisticated)
        words = text.lower().split()
        keywords = [w for w in words if len(w) > 3 and w.isalpha()]
        return keywords[:5]  # Top 5 keywords

    def _build_context(self, task: str, memories, symbols) -> str:
        """Build context string from memories and symbols"""
        context_parts = [f"Task: {task}\n"]

        if memories:
            context_parts.append("\nRelevant Knowledge:")
            for i, mem in enumerate(memories[:3], 1):
                context_parts.append(f"{i}. {mem.content[:100]}...")

        if symbols:
            context_parts.append("\nRelevant Code Symbols:")
            seen = set()
            for sym in symbols[:5]:
                if sym.qualified_name not in seen:
                    context_parts.append(
                        f"  - {sym.qualified_name} ({sym.kind.name}) "
                        f"in {sym.file_path}:{sym.start_line}"
                    )
                    seen.add(sym.qualified_name)

        return "\n".join(context_parts)

    async def _process_with_claude(self, task: str, context: str) -> str:
        """Process task using Claude Agent SDK"""
        print("\n🤖 Processing with Claude...")

        system_prompt = f"""You are a smart coding agent with access to:
- A persistent memory system (ContextOS)
- Indexed codebase with symbol-level search
- Previous task history and knowledge

Context:
{context}

Provide clear, actionable responses based on the available context."""

        try:
            response = ""
            async for message in query(
                prompt=task,
                options=ClaudeAgentOptions(
                    system_prompt=system_prompt,
                    permission_mode='acceptEdits',
                    cwd=str(self.workspace)
                )
            ):
                if hasattr(message, 'content'):
                    for block in message.content:
                        if hasattr(block, 'text'):
                            response += block.text

            return response
        except Exception as e:
            print(f"⚠️  Claude API error: {e}")
            return await self._process_locally(task, context)

    async def _process_locally(self, task: str, context: str) -> str:
        """Fallback: process task locally without Claude API"""
        print("\n🔧 Processing locally (fallback mode)...")

        result = f"""Task Analysis (Local Mode):
{context}

Note: This is a fallback response. With Claude API, this would be a
full AI-generated response based on the context above.

The agent has:
- Stored the task in memory (L2_TASK)
- Retrieved relevant previous knowledge
- Found relevant code symbols
- Built context for processing

All information is now available in ContextOS for future reference.
"""
        return result

    async def get_memory_summary(self) -> dict:
        """Get a summary of agent's memories"""
        # Search for recent tasks
        recent_tasks = self.contextos.search_memory(
            query="task",
            top_k=10
        )

        # Search for completed work
        completed = self.contextos.search_memory(
            query="result completed",
            top_k=10
        )

        return {
            "recent_tasks": len(recent_tasks),
            "completed_work": len(completed),
            "agent_id": self.agent_id
        }

    async def share_knowledge(self, knowledge: str, tags: list[str]) -> str:
        """Share knowledge with other agents in the team"""
        print(f"\n📤 Sharing knowledge with team...")

        memory_id = self.contextos.store_memory(
            content=knowledge,
            tier=MemoryTier.L3_SEMANTIC,
            scope=Scope.TEAM,  # Share with team
            tags=tags + ["shared", "team-knowledge"]
        )

        print(f"✅ Knowledge shared: {memory_id}")
        return memory_id

    async def learn_from_team(self, topic: str) -> list:
        """Learn from other agents' shared knowledge"""
        print(f"\n📥 Learning from team about: {topic}")

        team_knowledge = self.contextos.search_memory(
            query=topic,
            scope=Scope.TEAM,  # Only team-shared knowledge
            top_k=10
        )

        print(f"✅ Found {len(team_knowledge)} team memories")
        return team_knowledge

    async def stop(self):
        """Cleanup and shutdown"""
        print("\n👋 Shutting down agent...")
        self.contextos.disconnect()


async def demo_agent():
    """Run a demonstration of the agent"""
    print("=" * 70)
    print("🎯 Smart Code Agent with ContextOS Demo")
    print("=" * 70)

    # Create agent
    agent = SmartCodeAgent(
        agent_id="demo-agent-001",
        workspace=Path.cwd()
    )

    if not await agent.start():
        print("❌ Failed to start agent")
        return

    # Demo 1: Process a task
    result1 = await agent.process_task(
        "Analyze the memory storage implementation in ContextOS"
    )
    print(f"\n📄 Result:\n{result1}\n")

    await asyncio.sleep(1)

    # Demo 2: Process another task (will find previous context)
    result2 = await agent.process_task(
        "How does the indexer service work?"
    )
    print(f"\n📄 Result:\n{result2}\n")

    await asyncio.sleep(1)

    # Demo 3: Share knowledge
    await agent.share_knowledge(
        "ContextOS uses RocksDB for persistent storage and tree-sitter for AST parsing",
        tags=["architecture", "storage", "parsing"]
    )

    # Demo 4: Get memory summary
    summary = await agent.get_memory_summary()
    print(f"\n📊 Memory Summary:")
    print(f"   Recent tasks: {summary['recent_tasks']}")
    print(f"   Completed work: {summary['completed_work']}")

    # Cleanup
    await agent.stop()

    print("\n✅ Demo complete!")
    print("=" * 70)


async def main():
    """Main entry point"""
    if not AGENT_AVAILABLE:
        print("❌ ContextOS agent runner not available")
        print("Make sure run_contextos_agent.py is in the same directory")
        sys.exit(1)

    if len(sys.argv) > 1:
        # Process specific task
        task = " ".join(sys.argv[1:])

        agent = SmartCodeAgent(
            agent_id="cli-agent",
            workspace=Path.cwd()
        )

        if await agent.start():
            result = await agent.process_task(task)
            print(f"\n{'='*70}")
            print(f"📄 RESULT")
            print(f"{'='*70}")
            print(result)
            await agent.stop()
    else:
        # Run demo
        await demo_agent()


if __name__ == "__main__":
    asyncio.run(main())
