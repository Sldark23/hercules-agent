import { randomUUID } from 'node:crypto'
import { AgentRegistry } from './registry.js'
import { createTopology } from './topologies/index.js'
import type {
  AgentProfile, SwarmTask, SwarmRun, SwarmOrchestratorConfig,
  SwarmTopology, SwarmRunStatus, AgentCapability,
} from './types.js'
import type { TopologyExecutor } from './topologies/index.js'

export interface AgentRunner {
  (agentId: string, input: string): Promise<{ result: string; tokens: number; error?: string }>
}

export class SwarmOrchestrator {
  readonly registry: AgentRegistry
  private config: SwarmOrchestratorConfig
  private runs: Map<string, SwarmRun> = new Map()
  private executor: Map<string, TopologyExecutor> = new Map()
  private agentRunner?: AgentRunner

  constructor(config: Partial<SwarmOrchestratorConfig> = {}) {
    this.config = {
      maxConcurrentAgents: config.maxConcurrentAgents ?? 5,
      defaultMaxTurns: config.defaultMaxTurns ?? 10,
      storeRunHistory: config.storeRunHistory ?? true,
    }

    this.registry = new AgentRegistry()
  }

  setAgentRunner(runner: AgentRunner): void {
    this.agentRunner = runner
  }

  // ─── Agent Management ─────────────────────────────────────────

  registerAgent(profile: AgentProfile): void {
    this.registry.register(profile)
  }

  getAgent(id: string) {
    return this.registry.get(id)
  }

  listAgents(filter?: { state?: string; capability?: AgentCapability }) {
    return this.registry.list(filter as any)
  }

  removeAgent(id: string): boolean {
    return this.registry.remove(id)
  }

  // ─── Run Management ───────────────────────────────────────────

  createRun(options: {
    name: string
    topology: SwarmTopology
    tasks: Array<{ description: string; input: string; assignedAgentId?: string; priority?: number }>
    agentIds: string[]
  }): SwarmRun {
    const run: SwarmRun = {
      id: randomUUID(),
      name: options.name,
      topology: options.topology,
      status: 'pending',
      tasks: options.tasks.map(t => ({
        id: randomUUID(),
        description: t.description,
        input: t.input,
        assignedAgentId: t.assignedAgentId,
        status: 'pending',
        subtasks: [],
        priority: t.priority ?? 0,
        createdAt: new Date(),
        metadata: {},
      })),
      agents: options.agentIds,
    }

    if (this.config.storeRunHistory) {
      this.runs.set(run.id, run)
    }

    return run
  }

  async executeRun(runId: string): Promise<SwarmRun> {
    const run = this.runs.get(runId) || this.getRun(runId)
    if (!run) throw new Error(`Run "${runId}" not found`)

    const executor = this.getTopologyExecutor(run.topology)
    run.status = 'running'
    run.startedAt = new Date()

    try {
      const completedRun = await executor.execute(run, this.registry, async (task) => {
        return this.executeTask(task, run)
      })
      return completedRun
    } catch (err) {
      run.status = 'failed'
      run.error = (err as Error).message
      run.completedAt = new Date()
      return run
    }
  }

  private async executeTask(task: SwarmTask, run: SwarmRun): Promise<SwarmTask> {
    if (!this.agentRunner) {
      task.status = 'failed'
      task.error = 'No agent runner configured. Call setAgentRunner() first.'
      return task
    }

    const agentId = task.assignedAgentId || run.agents[0]
    if (!agentId) {
      task.status = 'failed'
      task.error = 'No agent assigned to task'
      return task
    }

    const agent = this.registry.get(agentId)
    if (!agent) {
      task.status = 'failed'
      task.error = `Agent "${agentId}" not found in registry`
      return task
    }

    try {
      this.registry.updateState(agentId, 'busy')
      const output = await this.agentRunner(agentId, task.input)
      this.registry.recordTurn(agentId)

      task.status = 'completed'
      task.completedAt = new Date()
      if (output.result) {
        task.metadata = { ...task.metadata, output: output.result }
      }
      return task
    } catch (err) {
      this.registry.recordError(agentId)
      task.status = 'failed'
      task.error = (err as Error).message
      return task
    } finally {
      this.registry.updateState(agentId, 'idle')
    }
  }

  private getTopologyExecutor(topology: SwarmTopology): TopologyExecutor {
    const key = topology
    let executor = this.executor.get(key)
    if (!executor) {
      executor = createTopology(topology)
      this.executor.set(key, executor)
    }
    return executor!
  }

  // ─── Query ────────────────────────────────────────────────────

  getRun(runId: string): SwarmRun | undefined {
    return this.runs.get(runId)
  }

  listRuns(filter?: { status?: SwarmRunStatus; topology?: SwarmTopology }): SwarmRun[] {
    let results = Array.from(this.runs.values())
    if (filter?.status) results = results.filter(r => r.status === filter.status)
    if (filter?.topology) results = results.filter(r => r.topology === filter.topology)
    return results.sort((a, b) => (b.startedAt?.getTime() ?? 0) - (a.startedAt?.getTime() ?? 0))
  }

  cancelRun(runId: string): boolean {
    const run = this.runs.get(runId)
    if (!run) return false
    run.status = 'cancelled'
    run.completedAt = new Date()
    return true
  }

  getStats() {
    const all = this.listRuns()
    return {
      totalAgents: this.registry.count(),
      totalRuns: all.length,
      completedRuns: all.filter(r => r.status === 'completed').length,
      failedRuns: all.filter(r => r.status === 'failed').length,
      runningRuns: all.filter(r => r.status === 'running').length,
      pendingRuns: all.filter(r => r.status === 'pending').length,
    }
  }
}
