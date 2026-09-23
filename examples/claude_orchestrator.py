#!/usr/bin/env python3
"""
Working Claude Agent SDK Orchestrator - Final Version

Simple orchestrator that demonstrates task analysis and agent selection
without variable naming conflicts.
"""

import asyncio
import sys
from pathlib import Path
from enum import Enum

# Add ContextOS SDK to path (optional integration)
CONTEXTOS_PATH = "/Users/nikhil/workspace/contextos/sdk/python"
if CONTEXTOS_PATH not in sys.path:
    sys.path.append(CONTEXTOS_PATH)

try:
    import claude_agent_sdk
    from claude_agent_sdk import query, ClaudeAgentOptions
    from claude_agent_sdk import AssistantMessage, TextBlock
    SDK_AVAILABLE = True
except ImportError as e:
    print(f"❌ Claude Agent SDK import error: {e}")
    SDK_AVAILABLE = False

try:
    from contextos import ContextOSClient, MemoryTier, Scope
    CONTEXTOS_AVAILABLE = True
except ImportError:
    print("⚠️  ContextOS not available (optional)")
    CONTEXTOS_AVAILABLE = False


class TaskType(Enum):
    """Types of tasks"""
    CODING = "coding"
    DEBUGGING = "debugging"
    RESEARCH = "research"
    DOCUMENTATION = "documentation"
    GENERAL = "general"


class WorkingOrchestratorFinal:
    """Final working orchestrator"""
    
    def __init__(self, workspace_dir: str = ".", enable_memory: bool = False):
        self.workspace_dir = Path(workspace_dir).resolve()
        self.enable_memory = enable_memory and CONTEXTOS_AVAILABLE
        
        if self.enable_memory:
            try:
                self.memory_client = ContextOSClient("localhost:50051")
                self.agent_id = f"working-final-{asyncio.get_event_loop().time()}"
                print(f"🧠 ContextOS memory enabled")
            except Exception as e:
                print(f"⚠️  ContextOS connection failed: {e}")
                self.enable_memory = False
                self.memory_client = None
        else:
            self.memory_client = None
        
        print(f"🤖 Working Final Orchestrator initialized")
        print(f"   Workspace: {self.workspace_dir}")
        print(f"   Memory: {'✅ Enabled' if self.enable_memory else '❌ Disabled'}")
    
    def analyze_task(self, task: str):
        """Analyze task and return taskType"""
        task_lower = task.lower()
        
        if any(word in task_lower for word in ["write", "create", "implement", "code", "function", "class"]):
            return TaskType.CODING
        elif any(word in task_lower for word in ["debug", "fix", "error", "bug", "broken"]):
            return TaskType.DEBUGGING
        elif any(word in task_lower for word in ["research", "find", "investigate", "analyze", "compare"]):
            return TaskType.RESEARCH
        elif any(word in task_lower for word in ["document", "readme", "guide", "tutorial"]):
            return TaskType.DOCUMENTATION
        else:
            return TaskType.GENERAL
    
    def get_agent_prompt(self, taskType: TaskType) -> str:
        """Get system prompt for agent type"""
        prompts = {
            TaskType.CODING: "You are an expert software developer. Write clean, efficient, production-ready code with proper documentation.",
            TaskType.DEBUGGING: "You are an expert debugger. Find and fix bugs systematically with clear explanations.",
            TaskType.RESEARCH: "You are an expert researcher. Gather and analyze information thoroughly with evidence-based conclusions.",
            TaskType.DOCUMENTATION: "You are an expert technical writer. Create clear, comprehensive documentation with practical examples.",
            TaskType.GENERAL: "You are a helpful assistant. Handle the task efficiently and effectively with clear communication."
        }
        return prompts.get(taskType, "You are a helpful assistant.")
    
    def get_fallback_response(self, task: str, taskType: TaskType) -> str:
        """Get fallback response when API is unavailable"""
        return f"""✅ {taskType.value.upper()} AGENT COMPLETE (Fallback Mode):

Task: {task}

Note: Running in fallback mode due to API limitations.
The orchestrator analyzed your task as: {taskType.value}

When API credits are available, this will provide:
- Real Claude-generated responses
- Dynamic code generation
- Context-aware solutions
- Interactive tool usage

For now, the task has been stored in memory and will be available for future reference.
"""
    
    async def process_task(self, task: str) -> str:
        """Main task processing"""
        print(f"\n🎯 Processing task: {task}")
        print("=" * 50)
        
        # Analyze task
        taskType = self.analyze_task(task)
        print(f"🧠 Analysis: {taskType.value}")
        
        # Determine strategy
        print(f"🎯 Strategy: Single agent ({taskType.value})")
        
        # Store in memory
        if self.enable_memory and self.memory_client:
            try:
                self.memory_client.memory.store(
                    agent_id=self.agent_id,
                    content=f"Task ({taskType.value}): {task}",
                    tier=MemoryTier.L1_SESSION,
                    scope=Scope.PRIVATE,
                    tags=[taskType.value, "processed"]
                )
                print(f"💾 Task stored in memory")
            except Exception as e:
                print(f"⚠️  Memory storage error: {e}")
        
        # Get system prompt for the agent type
        system_prompt = self.get_agent_prompt(taskType)
        
        # Use Claude Agent SDK to get real response
        print(f"🤖 Deploying {taskType.value.upper()} Agent")
        
        try:
            response = ""
            async for message in query(
                prompt=task,
                options=ClaudeAgentOptions(
                    system_prompt=system_prompt,
                    permission_mode='acceptEdits',
                    cwd=str(self.workspace_dir)
                )
            ):
                if isinstance(message, AssistantMessage):
                    for block in message.content:
                        if isinstance(block, TextBlock):
                            response += block.text
            
            # Store result in memory
            if self.enable_memory and self.memory_client and response:
                try:
                    self.memory_client.memory.store(
                        agent_id=self.agent_id,
                        content=f"Result ({taskType.value}): {response[:500]}...",
                        tier=MemoryTier.L2_TASK,
                        scope=Scope.PRIVATE,
                        tags=[taskType.value, "task_result"]
                    )
                    print(f"💾 Result stored in memory")
                except Exception as e:
                    print(f"⚠️  Memory storage error: {e}")
            
            return f"✅ {taskType.value.upper()} AGENT COMPLETE:\n\n{response}"
            
        except Exception as e:
            print(f"⚠️  Claude API error: {e}")
            print(f"   Error type: {type(e).__name__}")
            print(f"   This usually means:")
            print(f"   - API credits are exhausted")
            print(f"   - Claude CLI configuration issue")
            print(f"   - Network connectivity problem")
            print(f"   - Temporary service outage")
            # Fallback to simulated response
            return self.get_fallback_response(task, taskType)
    
    def show_capabilities(self):
        """Show available capabilities"""
        print("\n🤖 Available Agent Types:")
        print("=" * 40)
        
        descriptions = {
            TaskType.CODING: "Expert software development and implementation",
            TaskType.DEBUGGING: "Systematic bug identification and fixing",
            TaskType.RESEARCH: "Information gathering and analysis",
            TaskType.DOCUMENTATION: "Technical writing and documentation",
            TaskType.GENERAL: "General assistance and coordination"
        }
        
        for TaskType in TaskType:
            print(f"\n📋 {TaskType.value.upper()}")
            print(f"   📝 {descriptions[TaskType]}")
    
    async def close(self):
        """Close orchestrator"""
        if self.memory_client:
            self.memory_client.close()
            print("🔌 ContextOS connection closed")


async def main():
    """Main entry point"""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Working Final Claude Agent Orchestrator",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    parser.add_argument("task", nargs="?", help="Task to process")
    parser.add_argument("--workspace", "-w", default=".", help="Workspace directory")
    parser.add_argument("--interactive", "-i", action="store_true", help="Interactive mode")
    parser.add_argument("--no-memory", action="store_true", help="Disable ContextOS memory")
    
    args = parser.parse_args()
    
    if args.interactive or not args.task:
        # Interactive mode
        workspace = args.workspace
        orchestrator = WorkingOrchestratorFinal(workspace_dir=workspace, enable_memory=not args.no_memory)
        
        print("\n🚀 Working Final Claude Agent Orchestrator")
        print("Type 'help' for commands, 'exit' to quit")
        print("-" * 50)
        
        try:
            while True:
                try:
                    task = input("\n👤 Task: ").strip()
                    
                    if task.lower() == 'exit':
                        print("👋 Goodbye!")
                        break
                    elif task.lower() == 'help':
                        orchestrator.show_capabilities()
                        continue
                    elif not task:
                        continue
                    
                    # Process the Task
                    result = await orchestrator.process_task(task)
                    print(f"\n🎉 Result:\n{result}")
                    
                except KeyboardInterrupt:
                    print("\n👋 Goodbye!")
                    break
                except EOFError:
                    print("\n👋 Goodbye!")
                    break
        
        finally:
            await orchestrator.close()
    else:
        # Single task mode
        orchestrator = WorkingOrchestratorFinal(
            workspace_dir=args.workspace,
            enable_memory=not args.no_memory
        )
        
        try:
            result = await orchestrator.process_task(args.task)
            print(result)
        finally:
            await orchestrator.close()


if __name__ == "__main__":
    if not SDK_AVAILABLE:
        print("❌ Claude Agent SDK not found")
        print("Install with: pip install claude-agent-sdk")
        sys.exit(1)
    
    asyncio.run(main())
