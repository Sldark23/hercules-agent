# Multi-Agent Spawning module for Hercules Agent
# Sub-agent execution and orchestration

from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, Callable, Union
from enum import Enum
import asyncio
import logging
import uuid
import json
import os
from datetime import datetime

logger = logging.getLogger(__name__)


class AgentRole(Enum):
    """Agent roles"""
    ORCHESTRATOR = "orchestrator"  # Can spawn other agents
    LEAF = "leaf"                 # Focused worker, cannot delegate


class AgentStatus(Enum):
    """Agent status"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class AgentConfig:
    """Sub-agent configuration"""
    role: AgentRole = AgentRole.LEAF
    
    # Model settings
    provider: str = "openrouter"
    model: str = "openai/gpt-4o-mini"
    temperature: float = 0.7
    max_tokens: int = 4096
    
    # Execution
    timeout: int = 600  # seconds
    max_retries: int = 1
    
    # Toolsets
    toolsets: List[str] = field(default_factory=lambda: ["terminal", "file", "web"])
    
    # Context
    system_prompt: str = ""
    context: str = ""  # Injected context
    
    # Isolation
    use_isolation: bool = True  # Separate process/environment
    working_dir: str = ""


@dataclass
class AgentResult:
    """Result from sub-agent execution"""
    agent_id: str
    status: AgentStatus
    output: str = ""
    error: Optional[str] = None
    duration: float = 0
    tool_calls: List[Dict] = field(default_factory=list)
    metrics: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SubAgent:
    """Sub-agent definition"""
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    name: str = ""
    goal: str = ""
    config: AgentConfig = field(default_factory=AgentConfig)
    status: AgentStatus = AgentStatus.PENDING
    result: Optional[AgentResult] = None
    
    created_at: datetime = field(default_factory=datetime.now)
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None


# ==================== Agent Executor ====================

class AgentExecutor:
    """Executes sub-agent tasks"""
    
    def __init__(self):
        self._running: Dict[str, asyncio.Task] = {}
    
    async def execute(
        self,
        agent: SubAgent,
        executor_fn: Callable[[str, List[str], Optional[Dict]], Any]
    ) -> AgentResult:
        """Execute agent task"""
        start_time = datetime.now()
        
        agent.status = AgentStatus.RUNNING
        agent.started_at = start_time
        
        try:
            # Execute with timeout
            output = await asyncio.wait_for(
                executor_fn(
                    agent.goal,
                    agent.config.toolsets,
                    {
                        "provider": agent.config.provider,
                        "model": agent.config.model,
                        "temperature": agent.config.temperature,
                        "max_tokens": agent.config.max_tokens,
                        "system_prompt": agent.config.system_prompt,
                    }
                ),
                timeout=agent.config.timeout
            )
            
            duration = (datetime.now() - start_time).total_seconds()
            
            result = AgentResult(
                agent_id=agent.id,
                status=AgentStatus.COMPLETED,
                output=output,
                duration=duration,
            )
            
            agent.status = AgentStatus.COMPLETED
            agent.result = result
            
            return result
            
        except asyncio.TimeoutError:
            agent.status = AgentStatus.FAILED
            
            result = AgentResult(
                agent_id=agent.id,
                status=AgentStatus.FAILED,
                error="Execution timeout",
                duration=agent.config.timeout,
            )
            agent.result = result
            
            return result
            
        except Exception as e:
            agent.status = AgentStatus.FAILED
            
            result = AgentResult(
                agent_id=agent.id,
                status=AgentStatus.FAILED,
                error=str(e),
                duration=(datetime.now() - start_time).total_seconds(),
            )
            agent.result = result
            
            return result
        
        finally:
            agent.finished_at = datetime.now()
    
    def cancel(self, agent_id: str):
        """Cancel running agent"""
        if agent_id in self._running:
            self._running[agent_id].cancel()
            self._running.pop(agent_id, None)


# ==================== Multi-Agent Manager ====================

class MultiAgentManager:
    """Manages multiple sub-agents"""
    
    def __init__(
        self,
        executor_fn: Callable = None,  # Main agent executor
        max_concurrent: int = 3,
        max_spawn_depth: int = 2
    ):
        self.executor_fn = executor_fn
        self.max_concurrent = max_concurrent
        self.max_spawn_depth = max_spawn_depth
        
        self._agents: Dict[str, SubAgent] = {}
        self._children: Dict[str, List[str]] = {}  # parent_id -> [child_ids]
        self._executor = AgentExecutor()
        self._semaphore = asyncio.Semaphore(max_concurrent)
    
    async def spawn(
        self,
        goal: str,
        name: str = "",
        config: AgentConfig = None,
        parent_id: str = None,
        context: str = ""
    ) -> SubAgent:
        """Spawn a new sub-agent"""
        agent = SubAgent(
            name=name or f"agent-{len(self._agents) + 1}",
            goal=goal,
            config=config or AgentConfig(),
        )
        
        # Inject context
        if context:
            agent.config.context = context
        
        # Register agent
        self._agents[agent.id] = agent
        
        # Track parent-child relationship
        if parent_id:
            if parent_id not in self._children:
                self._children[parent_id] = []
            self._children[parent_id].append(agent.id)
        
        logger.info(f"Spawned agent: {agent.name} ({agent.id})")
        
        return agent
    
    async def execute(
        self,
        agent_id: str,
        wait: bool = True
    ) -> AgentResult:
        """Execute an agent"""
        agent = self._agents.get(agent_id)
        if not agent:
            raise ValueError(f"Agent not found: {agent_id}")
        
        if not self.executor_fn:
            raise RuntimeError("Executor function not configured")
        
        async with self._semaphore:
            # Build context from parent
            context = agent.config.context
            if agent.id in self._children:
                # Include children's outputs
                for child_id in self._children[agent.id]:
                    child = self._agents.get(child_id)
                    if child and child.result:
                        context += f"\n\n[Child {child.name}]:\n{child.result.output}"
            
            full_goal = f"{context}\n\n{agent.goal}" if context else agent.goal
            
            return await self._executor.execute(agent, self.executor_fn)
    
    async def execute_parallel(
        self,
        agent_ids: List[str],
        wait: bool = True
    ) -> List[AgentResult]:
        """Execute multiple agents in parallel"""
        tasks = [self.execute(agent_id, wait) for agent_id in agent_ids]
        
        if wait:
            return await asyncio.gather(*tasks, return_exceptions=True)
        
        # Don't wait - fire and forget
        for task in tasks:
            asyncio.create_task(task)
        
        return []
    
    async def cancel(self, agent_id: str):
        """Cancel an agent"""
        agent = self._agents.get(agent_id)
        if not agent:
            return
        
        # Cancel all children first
        if agent_id in self._children:
            for child_id in self._children[agent_id]:
                await self.cancel(child_id)
        
        self._executor.cancel(agent_id)
        agent.status = AgentStatus.CANCELLED
        
        logger.info(f"Cancelled agent: {agent_id}")
    
    def get_agent(self, agent_id: str) -> Optional[SubAgent]:
        """Get agent by ID"""
        return self._agents.get(agent_id)
    
    def get_children(self, parent_id: str) -> List[SubAgent]:
        """Get child agents"""
        child_ids = self._children.get(parent_id, [])
        return [self._agents[cid] for cid in child_ids if cid in self._agents]
    
    def get_tree(self, root_id: str = None) -> Dict[str, Any]:
        """Get agent tree structure"""
        if not root_id:
            # Get root agents (no parent)
            roots = [
                a for a in self._agents.values()
                if a.id not in self._children
            ]
            if not roots:
                return {}
            root_id = roots[0].id
        
        root = self._agents.get(root_id)
        if not root:
            return {}
        
        def build_tree(agent_id: str) -> Dict:
            agent = self._agents.get(agent_id)
            if not agent:
                return {}
            
            return {
                "id": agent.id,
                "name": agent.name,
                "status": agent.status.value,
                "goal": agent.goal[:100],
                "children": [
                    build_tree(cid)
                    for cid in self._children.get(agent_id, [])
                ]
            }
        
        return build_tree(root_id)
    
    def list_agents(
        self,
        status: AgentStatus = None,
        role: AgentRole = None
    ) -> List[Dict[str, Any]]:
        """List agents with optional filters"""
        agents = list(self._agents.values())
        
        if status:
            agents = [a for a in agents if a.status == status]
        
        return [
            {
                "id": a.id,
                "name": a.name,
                "status": a.status.value,
                "role": a.config.role.value if role else "N/A",
                "created_at": a.created_at.isoformat(),
                "duration": (a.finished_at - a.started_at).total_seconds()
                if a.finished_at and a.started_at else None,
            }
            for a in agents
        ]
    
    def get_stats(self) -> Dict[str, Any]:
        """Get execution statistics"""
        total = len(self._agents)
        by_status = {}
        
        for agent in self._agents.values():
            status = agent.status.value
            by_status[status] = by_status.get(status, 0) + 1
        
        return {
            "total_agents": total,
            "by_status": by_status,
            "max_concurrent": self.max_concurrent,
            "running": len([a for a in self._agents.values() if a.status == AgentStatus.RUNNING]),
        }
    
    def clear(self, status: AgentStatus = None):
        """Clear agents"""
        if status:
            to_remove = [
                a.id for a in self._agents.values()
                if a.status == status
            ]
            for agent_id in to_remove:
                del self._agents[agent_id]
        else:
            self._agents.clear()
            self._children.clear()


# ==================== Orchestrator Pattern ====================

class AgentOrchestrator:
    """Orchestrates multiple sub-agents"""
    
    def __init__(self, manager: MultiAgentManager = None):
        self.manager = manager or MultiAgentManager()
    
    async def parallel_execution(
        self,
        tasks: List[Dict[str, Any]]  # [{goal, name, config}]
    ) -> List[AgentResult]:
        """Execute tasks in parallel"""
        # Spawn all agents
        agent_ids = []
        for task in tasks:
            agent = await self.manager.spawn(
                goal=task["goal"],
                name=task.get("name"),
                config=task.get("config"),
            )
            agent_ids.append(agent.id)
        
        # Execute in parallel
        return await self.manager.execute_parallel(agent_ids)
    
    async def sequential_execution(
        self,
        tasks: List[Dict[str, Any]],
        pass_output: bool = True
    ) -> List[AgentResult]:
        """Execute tasks sequentially, optionally passing output"""
        results = []
        context = ""
        
        for task in tasks:
            # Inject previous context if enabled
            if pass_output and context:
                task["context"] = context
            
            # Spawn and execute
            agent = await self.manager.spawn(
                goal=task["goal"],
                name=task.get("name"),
                config=task.get("config"),
                context=task.get("context", ""),
            )
            
            result = await self.manager.execute(agent.id)
            results.append(result)
            
            # Update context
            if pass_output and result.output:
                context += f"\n\n[{agent.name}]:\n{result.output}"
        
        return results
    
    async def map_reduce(
        self,
        items: List[Any],
        map_fn: Callable,  # (item) -> goal
        reduce_fn: Callable,  # (results) -> final_goal
        map_config: AgentConfig = None
    ) -> AgentResult:
        """Map-reduce pattern"""
        # Map phase - execute for each item
        map_tasks = [
            {"goal": map_fn(item), "config": map_config}
            for item in items
        ]
        
        map_results = await self.parallel_execution(map_tasks)
        
        # Reduce phase - combine results
        reduce_goal = reduce_fn([r.output for r in map_results])
        
        reduce_agent = await self.manager.spawn(goal=reduce_goal)
        reduce_result = await self.manager.execute(reduce_agent.id)
        
        return reduce_result
    
    async def explore_parallel(
        self,
        goal: str,
        num_explorers: int = 3,
        config: AgentConfig = None
    ) -> List[AgentResult]:
        """Explore with multiple agents in parallel"""
        variations = [
            f"{goal} (approach {i+1})"
            for i in range(num_explorers)
        ]
        
        tasks = [
            {"goal": v, "config": config}
            for v in variations
        ]
        
        return await self.parallel_execution(tasks)
    
    async def vote(
        self,
        goal: str,
        num_agents: int = 3,
        config: AgentConfig = None
    ) -> str:
        """Multiple agents vote on best approach"""
        results = await self.explore_parallel(goal, num_agents, config)
        
        # Combine all approaches
        combined = "\n\n".join([
            f"Option {i+1}:\n{r.output}"
            for i, r in enumerate(results)
        ])
        
        # Have one agent decide
        decide_agent = await self.manager.spawn(
            goal=f"""Given these approaches, choose the best one and explain why:

{combined}

Best approach:"""
        )
        
        decide_result = await self.manager.execute(decide_agent.id)
        
        return decide_result.output