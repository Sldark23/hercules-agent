import { describe, it, expect } from 'vitest'
import { CredentialPool } from './credential-pool.js'
import { ContextEngine } from './context-engine.js'
import { assembleSystemPrompt } from './system-prompt.js'
import { SimpleTelemetry, createAgentTelemetry } from './opentelemetry.js'
import type { Message, SystemPromptConfig, ToolDefinition } from './types.js'

describe('Core Integration: CredentialPool + ContextEngine', () => {
  it('manages credentials and context together', async () => {
    const pool = new CredentialPool()
    pool.register({ id: 'c1', providerId: 'anthropic', apiKey: 'sk-ant-xxx', isActive: true, failureCount: 0 })

    const engine = new ContextEngine({ maxTokens: 5000 })
    engine.init('sess-int-1')

    await engine.addMessage('sess-int-1', {
      id: 'm1', role: 'user', content: 'Hello from integration test', createdAt: new Date(),
    })

    const credential = pool.getActive('anthropic')
    expect(credential).toBeDefined()
    expect(credential!.apiKey).toBe('sk-ant-xxx')

    const state = engine.getState('sess-int-1')
    expect(state?.messages).toHaveLength(1)
    expect(state?.usedTokens).toBeGreaterThan(0)
  })
})

describe('Core Integration: SystemPrompt + Telemetry', () => {
  it('builds prompt and records telemetry', () => {
    const config: SystemPromptConfig = {
      persona: 'You are a test agent.',
      skills: [{ name: 'test-skill', content: 'Do testing', priority: 1 }],
      constraints: ['Be fast'],
    }

    const tools: ToolDefinition[] = [{
      name: 'ping',
      description: 'Ping tool',
      inputSchema: { safeParse: () => ({ success: true, data: {} }) } as unknown as ToolDefinition['inputSchema'],
      handler: async () => ({ toolCallId: 't1', output: 'pong' }),
    }]

    const assembly = assembleSystemPrompt(config, tools)
    expect(assembly.system).toContain('test agent')
    expect(assembly.system).toContain('test-skill')
    expect(assembly.system).toContain('ping')

    const agentTel = createAgentTelemetry('test-agent')
    agentTel.telemetry.recordEvent('prompt_built', { modelId: 'test-model' })
    agentTel.telemetry.recordMetric('prompt_length', assembly.system.length, 'chars')

    const events = agentTel.telemetry.getEvents()
    expect(events).toHaveLength(1)
    expect(events[0]!.name).toBe('prompt_built')

    const metrics = agentTel.telemetry.getMetrics()
    expect(metrics).toHaveLength(1)
    expect(metrics[0]!.name).toBe('prompt_length')
  })
})

describe('Core Integration: CredentialPool rotation', () => {
  it('round-robins across multiple credentials', () => {
    const pool = new CredentialPool({ rotationStrategy: 'round-robin', maxRetriesPerKey: 2, cooldownMinutes: 5 })
    pool.register({ id: 'k1', providerId: 'openai', apiKey: 'key-1', isActive: true, failureCount: 0 })
    pool.register({ id: 'k2', providerId: 'openai', apiKey: 'key-2', isActive: true, failureCount: 0 })

    const first = pool.getActive('openai')!
    pool.recordSuccess(first.id)
    const second = pool.getActive('openai')!
    expect(first.id).not.toBe(second.id)

    pool.recordSuccess(second.id)
    const third = pool.getActive('openai')!
    expect(third.id).toBe(first.id)
  })
})
