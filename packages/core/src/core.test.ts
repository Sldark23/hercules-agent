import { describe, it, expect, beforeEach } from 'vitest'
import { CredentialPool } from './credential-pool.js'
import { ContextEngine } from './context-engine.js'
import { assembleSystemPrompt } from './system-prompt.js'
import type { Credential, Message, SystemPromptConfig, ToolDefinition } from './types.js'

// ─── CredentialPool ────────────────────────────────────────────────

describe('CredentialPool', () => {
  let pool: CredentialPool

  beforeEach(() => {
    pool = new CredentialPool({ maxRetriesPerKey: 2, cooldownMinutes: 1 })
  })

  it('registers and retrieves credentials', () => {
    pool.register({ id: 'c1', providerId: 'anthropic', apiKey: 'sk-ant-xxx', isActive: true, failureCount: 0 })
    expect(pool.getActive('anthropic')?.apiKey).toBe('sk-ant-xxx')
  })

  it('returns undefined when no credentials available', () => {
    expect(pool.getActive('openai')).toBeUndefined()
  })

  it('deactivates credential after max retries', () => {
    pool.register({ id: 'c1', providerId: 'anthropic', apiKey: 'sk-ant-xxx', isActive: true, failureCount: 0 })
    pool.recordFailure('c1')
    pool.recordFailure('c1')
    expect(pool.getActive('anthropic')).toBeUndefined()
  })

  it('rotates between multiple credentials', () => {
    pool.register({ id: 'c1', providerId: 'openai', apiKey: 'key-1', isActive: true, failureCount: 0 })
    pool.register({ id: 'c2', providerId: 'openai', apiKey: 'key-2', isActive: true, failureCount: 0 })

    const first = pool.getActive('openai')!
    const second = pool.getActive('openai')!
    expect(first.id).toBe(second.id)
  })
})

// ─── ContextEngine ─────────────────────────────────────────────────

describe('ContextEngine', () => {
  let engine: ContextEngine

  beforeEach(() => {
    engine = new ContextEngine({ maxTokens: 1000, compressionThreshold: 0.8, maxMessages: 10 })
  })

  it('initializes session state', () => {
    engine.init('sess-1')
    const state = engine.getState('sess-1')
    expect(state?.sessionId).toBe('sess-1')
    expect(state?.messages).toHaveLength(0)
  })

  it('adds messages and tracks token usage', async () => {
    engine.init('sess-1')
    await engine.addMessage('sess-1', {
      id: 'm1', role: 'user', content: 'hello world', createdAt: new Date(),
    })
    const state = engine.getState('sess-1')
    expect(state?.messages).toHaveLength(1)
    expect(state?.usedTokens).toBeGreaterThan(0)
  })

  it('compresses when exceeding threshold', async () => {
    engine.init('sess-1')
    for (let i = 0; i < 12; i++) {
      await engine.addMessage('sess-1', {
        id: `m${i}`, role: 'user', content: 'A'.repeat(100), createdAt: new Date(),
      })
    }
    const state = engine.getState('sess-1')
    expect(state?.isCompressed).toBe(true)
  })

  it('returns context window within token budget', async () => {
    engine.init('sess-1')
    for (let i = 0; i < 5; i++) {
      await engine.addMessage('sess-1', {
        id: `m${i}`, role: 'user', content: 'word '.repeat(20), createdAt: new Date(),
      })
    }
    const window = engine.getWindow('sess-1', 50)
    expect(window.length).toBeLessThan(5)
  })
})

// ─── SystemPrompt ──────────────────────────────────────────────────

describe('assembleSystemPrompt', () => {
  it('builds prompt from config', () => {
    const config: SystemPromptConfig = {
      persona: 'You are a helpful AI assistant.',
      skills: [{ name: 'coding', content: 'Expert in TypeScript', priority: 1 }],
      constraints: ['Be concise'],
    }
    const tools: ToolDefinition[] = [{
      name: 'read_file',
      description: 'Read a file',
      inputSchema: { type: 'object', properties: { path: {} } } as unknown as ToolDefinition['inputSchema'],
      handler: async () => ({ toolCallId: 't1', output: '' }),
    }]

    const result = assembleSystemPrompt(config, tools)
    expect(result.system).toContain('Persona')
    expect(result.system).toContain('coding')
    expect(result.system).toContain('read_file')
    expect(result.system).toContain('Be concise')
  })
})
