import { randomUUID } from 'node:crypto'
import type { SwarmTask, SwarmRun, DelegationResult, AgentCapability } from '../types.js'
import type { AgentRegistry } from '../registry.js'

export interface TopologyExecutor {
  name: string
  execute(run: SwarmRun, registry: AgentRegistry, executeTask: (task: SwarmTask) => Promise<SwarmTask>): Promise<SwarmRun>
}

// ─── Sequential ─────────────────────────────────────────────────

export class SequentialTopology implements TopologyExecutor {
  readonly name = 'sequential'

  async execute(
    run: SwarmRun,
    registry: AgentRegistry,
    executeTask: (task: SwarmTask) => Promise<SwarmTask>
  ): Promise<SwarmRun> {
    for (const task of run.tasks) {
      task.startedAt = new Date()
      task.status = 'running'

      run.status = 'running'
      const result = await executeTask(task)

      if (result.status === 'failed') {
        run.status = 'failed'
        run.error = `Task "${task.description}" failed: ${result.error}`
        return run
      }
    }

    run.status = 'completed'
    run.completedAt = new Date()
    return run
  }
}

// ─── Hierarchical ───────────────────────────────────────────────

export class HierarchicalTopology implements TopologyExecutor {
  readonly name = 'hierarchical'

  async execute(
    run: SwarmRun,
    registry: AgentRegistry,
    executeTask: (task: SwarmTask) => Promise<SwarmTask>
  ): Promise<SwarmRun> {
    const manager = registry.get(run.agents[0]!)
    if (!manager) {
      run.status = 'failed'
      run.error = 'Manager agent not found'
      return run
    }

    run.status = 'running'

    for (const task of run.tasks) {
      if (registry.list({ state: 'idle' }).length === 0) {
        run.status = 'failed'
        run.error = 'No idle worker agents available'
        return run
      }

      task.startedAt = new Date()
      task.status = 'running'
      const result = await executeTask(task)

      if (result.status === 'failed') {
        run.error = `Task "${task.description}" failed: ${result.error}`
        run.status = 'failed'
        return run
      }
    }

    run.status = 'completed'
    run.completedAt = new Date()
    return run
  }
}

// ─── Router ─────────────────────────────────────────────────────

export class RouterTopology implements TopologyExecutor {
  readonly name = 'router'

  async execute(
    run: SwarmRun,
    registry: AgentRegistry,
    executeTask: (task: SwarmTask) => Promise<SwarmTask>
  ): Promise<SwarmRun> {
    run.status = 'running'

    for (const task of run.tasks) {
      if (!task.assignedAgentId) {
        const best = registry.findBestMatch(registry.list().map(a => a.profile.capabilities[0]!).filter(Boolean), ['*'])
        if (best) {
          task.assignedAgentId = best.profile.id
        }
      }

      task.startedAt = new Date()
      task.status = 'running'
      const result = await executeTask(task)

      if (result.status === 'failed') {
        run.error = `Task "${task.description}" failed: ${result.error}`
        run.status = 'failed'
        return run
      }
    }

    run.status = 'completed'
    run.completedAt = new Date()
    return run
  }

  delegate(
    task: SwarmTask,
    registry: AgentRegistry,
    requiredCapabilities: AgentCapability[]
  ): DelegationResult {
    const best = registry.findBestMatch(registry.list().map(a => a.profile.capabilities).flat(), requiredCapabilities)

    if (!best) {
      return {
        taskId: task.id,
        agentId: '',
        confidence: 0,
        reason: 'No suitable agent found',
      }
    }

    const matchedCapabilities = requiredCapabilities.filter(req =>
      best.profile.capabilities.some(c => c.toLowerCase() === req.toLowerCase())
    )

    return {
      taskId: task.id,
      agentId: best.profile.id,
      confidence: matchedCapabilities.length / requiredCapabilities.length,
      reason: `Agent "${best.profile.name}" matches capabilities: ${matchedCapabilities.join(', ')}`,
    }
  }
}

// ─── Factory ────────────────────────────────────────────────────

export function createTopology(type: string): TopologyExecutor {
  switch (type) {
    case 'sequential': return new SequentialTopology()
    case 'hierarchical': return new HierarchicalTopology()
    case 'router': return new RouterTopology()
    default: throw new Error(`Unknown topology: "${type}"`)
  }
}
