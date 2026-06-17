import { describe, it, expect, beforeEach } from 'vitest'
import { AgentRegistry } from './registry.js'
import { SwarmOrchestrator } from './orchestrator.js'
import { SequentialTopology, HierarchicalTopology, RouterTopology } from './topologies/index.js'
import type { AgentProfile, SwarmTask, SwarmRun } from './types.js'

function makeProfile(overrides: Partial<AgentProfile> = {}): AgentProfile {
  return {
    id: overrides.id ?? '',
    name: overrides.name ?? 'test-agent',
    role: overrides.role ?? 'worker',
    description: overrides.description ?? 'A test agent',
    capabilities: overrides.capabilities ?? ['general'],
    modelId: overrides.modelId ?? 'gpt-4',
    systemPrompt: overrides.systemPrompt ?? 'You are a test agent.',
    tools: overrides.tools ?? [],
    maxTurns: overrides.maxTurns ?? 5,
    temperature: overrides.temperature ?? 0.7,
    weight: overrides.weight ?? 1,
  }
}

// ─── AgentRegistry ──────────────────────────────────────────────

describe('AgentRegistry', () => {
  let registry: AgentRegistry

  beforeEach(() => { registry = new AgentRegistry() })

  it('registers an agent', () => {
    const agent = registry.register(makeProfile({ name: 'alice', capabilities: ['code', 'analysis'] }))
    expect(agent.profile.id).toBeDefined()
    expect(agent.state).toBe('idle')
    expect(agent.profile.capabilities).toContain('code')
    expect(registry.count()).toBe(1)
  })

  it('rejects duplicate registration', () => {
    registry.register(makeProfile({ id: 'a1' }))
    expect(() => registry.register(makeProfile({ id: 'a1' }))).toThrow('already registered')
  })

  it('finds agents by capability', () => {
    registry.register(makeProfile({ name: 'coder', capabilities: ['code'] }))
    registry.register(makeProfile({ name: 'writer', capabilities: ['writing'] }))

    const coders = registry.list({ capability: 'code' })
    expect(coders).toHaveLength(1)
    expect(coders[0]!.profile.name).toBe('coder')
  })

  it('finds best match by capability', () => {
    registry.register(makeProfile({ name: 'general', capabilities: ['code', 'writing'] }))
    registry.register(makeProfile({ name: 'specialist', capabilities: ['code', 'debugging', 'review'] }))

    const best = registry.findBestMatch(['code', 'writing'], ['code', 'debugging', 'review'])
    expect(best).toBeDefined()
    expect(best!.profile.name).toBe('specialist')
  })

  it('returns undefined for best match when no idle agents', () => {
    const a = registry.register(makeProfile())
    registry.updateState(a.profile.id, 'busy')
    expect(registry.findBestMatch(['general'], ['general'])).toBeUndefined()
  })

  it('updates agent state', () => {
    const a = registry.register(makeProfile())
    registry.updateState(a.profile.id, 'busy')
    expect(registry.get(a.profile.id)!.state).toBe('busy')
    expect(registry.get(a.profile.id)!.lastActiveAt).toBeDefined()
  })

  it('tracks turns and errors', () => {
    const a = registry.register(makeProfile())
    registry.recordTurn(a.profile.id)
    registry.recordTurn(a.profile.id)
    registry.recordError(a.profile.id)
    expect(registry.get(a.profile.id)!.totalTurns).toBe(2)
    expect(registry.get(a.profile.id)!.errorCount).toBe(1)
  })
})

// ─── SwarmOrchestrator ──────────────────────────────────────────

describe('SwarmOrchestrator', () => {
  let orchestrator: SwarmOrchestrator

  let agentARuns = 0
  let agentBRuns = 0

  beforeEach(() => {
    agentARuns = 0
    agentBRuns = 0

    orchestrator = new SwarmOrchestrator({ storeRunHistory: true })

    orchestrator.registerAgent(makeProfile({
      id: 'agent-a', name: 'Worker A', capabilities: ['code', 'analysis'],
    }))
    orchestrator.registerAgent(makeProfile({
      id: 'agent-b', name: 'Worker B', capabilities: ['writing', 'creative'],
    }))
    orchestrator.registerAgent(makeProfile({
      id: 'manager', name: 'Manager', capabilities: ['planning', 'review'],
    }))

    orchestrator.setAgentRunner(async (agentId, input) => {
      if (agentId === 'agent-a') agentARuns++
      if (agentId === 'agent-b') agentBRuns++
      return { result: `${agentId} processed: ${input}`, tokens: 100 }
    })
  })

  it('registers and lists agents', () => {
    expect(orchestrator.listAgents()).toHaveLength(3)
    expect(orchestrator.getAgent('agent-a')).toBeDefined()
    expect(orchestrator.removeAgent('nonexistent')).toBe(false)
  })

  it('removes an agent', () => {
    expect(orchestrator.removeAgent('agent-a')).toBe(true)
    expect(orchestrator.listAgents()).toHaveLength(2)
  })

  it('creates a run', () => {
    const run = orchestrator.createRun({
      name: 'test-run',
      topology: 'sequential',
      tasks: [
        { description: 'Write code', input: 'implement feature X' },
        { description: 'Review code', input: 'review the implementation' },
      ],
      agentIds: ['agent-a', 'agent-b'],
    })

    expect(run.id).toBeDefined()
    expect(run.tasks).toHaveLength(2)
    expect(run.status).toBe('pending')
    expect(run.topology).toBe('sequential')
  })

  it('executes sequential run', async () => {
    const run = orchestrator.createRun({
      name: 'sequential-test',
      topology: 'sequential',
      tasks: [
        { description: 'Task 1', input: 'do thing 1', assignedAgentId: 'agent-a' },
        { description: 'Task 2', input: 'do thing 2', assignedAgentId: 'agent-b' },
      ],
      agentIds: ['agent-a', 'agent-b'],
    })

    const result = await orchestrator.executeRun(run.id)
    expect(result.status).toBe('completed')
    expect(result.tasks.every(t => t.status === 'completed')).toBe(true)
    expect(agentARuns).toBe(1)
    expect(agentBRuns).toBe(1)
  })

  it('fails run when no agent runner configured', async () => {
    const bad = new SwarmOrchestrator()
    bad.registerAgent(makeProfile({ id: 'x' }))

    const run = bad.createRun({
      name: 'bad', topology: 'sequential',
      tasks: [{ description: 't', input: 'i' }],
      agentIds: ['x'],
    })

    const result = await bad.executeRun(run.id)
    expect(result.status).toBe('failed')
    expect(result.error).toContain('No agent runner')
  })

  it('fails run on invalid agent id', async () => {
    const run = orchestrator.createRun({
      name: 'invalid', topology: 'sequential',
      tasks: [{ description: 't', input: 'i', assignedAgentId: 'nonexistent' }],
      agentIds: ['nonexistent'],
    })

    const result = await orchestrator.executeRun(run.id)
    expect(result.status).toBe('failed')
    expect(result.error).toContain('not found in registry')
  })

  it('cancels a running run', () => {
    const run = orchestrator.createRun({
      name: 'cancel-test', topology: 'sequential',
      tasks: [{ description: 't', input: 'i' }],
      agentIds: ['agent-a'],
    })

    expect(orchestrator.cancelRun(run.id)).toBe(true)
    expect(orchestrator.getRun(run.id)!.status).toBe('cancelled')
  })

  it('returns stats', () => {
    expect(orchestrator.getStats().totalAgents).toBe(3)
    expect(orchestrator.getStats().totalRuns).toBe(0)
  })

  it('lists runs with filters', async () => {
    const r1 = orchestrator.createRun({
      name: 'r1', topology: 'sequential',
      tasks: [{ description: 't', input: 'i', assignedAgentId: 'agent-a' }],
      agentIds: ['agent-a'],
    })
    await orchestrator.executeRun(r1.id)

    expect(orchestrator.listRuns()).toHaveLength(1)
    expect(orchestrator.listRuns({ status: 'completed' })).toHaveLength(1)
    expect(orchestrator.listRuns({ status: 'failed' })).toHaveLength(0)
  })
})

// ─── Topologies ─────────────────────────────────────────────────

describe('SequentialTopology', () => {
  it('executes tasks sequentially', async () => {
    const order: number[] = []
    const topology = new SequentialTopology()

    const run: SwarmRun = {
      id: 'r1', name: 'test', topology: 'sequential',
      status: 'pending', tasks: [
        makeTask('1', 'task1'),
        makeTask('2', 'task2'),
      ],
      agents: ['a'],
    }

    const result = await topology.execute(run, new AgentRegistry(), async (task) => {
      order.push(Number(task.id))
      task.status = 'completed'
      return task
    })

    expect(order).toEqual([1, 2])
    expect(result.status).toBe('completed')
  })
})

function makeTask(id: string, desc: string): SwarmTask {
  return {
    id, description: desc, input: 'input',
    status: 'pending', subtasks: [], priority: 0,
    createdAt: new Date(),
  }
}
