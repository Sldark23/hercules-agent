import { describe, it, expect, beforeEach, afterEach } from 'vitest'
import { SessionStore } from './stores/session-store.js'
import { VectorStore } from './stores/vector-store.js'
import { UserProfileStore } from './stores/user-profile-store.js'
import { SupermemoryClient } from './supermemory/client.js'
import { MemoryManager } from './manager.js'
import { mkdtemp, rm } from 'node:fs/promises'
import { join } from 'node:path'
import { tmpdir } from 'node:os'
import { LocalEmbeddingProvider } from './stores/embeddings.js'

const testDir = join(tmpdir(), `memory-test-${Date.now()}`)

// ─── SessionStore ──────────────────────────────────────────────────

describe('SessionStore', () => {
  let store: SessionStore

  beforeEach(async () => {
    await mkdtemp(testDir)
    store = new SessionStore({ dbPath: join(testDir, 'sessions.json') })
    await store.init()
  })

  afterEach(async () => {
    await store.close()
    await rm(testDir, { recursive: true, force: true })
  })

  it('saves and retrieves sessions', async () => {
    await store.saveSession({
      id: 's1', messageCount: 0, tokenCount: 0, tags: [],
      createdAt: new Date(), updatedAt: new Date(),
    })
    expect(store.getSession('s1')).toBeDefined()
    expect(store.count().sessions).toBe(1)
  })

  it('adds messages to sessions', async () => {
    await store.saveSession({ id: 's2', messageCount: 0, tokenCount: 0, tags: [], createdAt: new Date(), updatedAt: new Date() })
    await store.addMessage({ id: 'm1', sessionId: 's2', role: 'user', content: 'hello', tokenCount: 5, timestamp: new Date() })
    const msgs = store.getMessages('s2')
    expect(msgs).toHaveLength(1)
    expect(msgs[0]!.content).toBe('hello')
  })

  it('searches sessions', async () => {
    await store.saveSession({ id: 's3', title: 'test session', messageCount: 1, tokenCount: 10, tags: [], createdAt: new Date(), updatedAt: new Date() })
    await store.addMessage({ id: 'm2', sessionId: 's3', role: 'user', content: 'discussing typescript', tokenCount: 5, timestamp: new Date() })
    const results = await store.searchSessions('typescript')
    expect(results).toHaveLength(1)
    expect(results[0]!.sessionId).toBe('s3')
  })

  it('lists sessions by user', async () => {
    await store.saveSession({ id: 'a', userId: 'u1', messageCount: 0, tokenCount: 0, tags: [], createdAt: new Date(), updatedAt: new Date() })
    await store.saveSession({ id: 'b', userId: 'u2', messageCount: 0, tokenCount: 0, tags: [], createdAt: new Date(), updatedAt: new Date() })
    expect(store.listSessions('u1')).toHaveLength(1)
  })
})

// ─── VectorStore ───────────────────────────────────────────────────

describe('VectorStore', () => {
  let store: VectorStore

  beforeEach(() => {
    store = new VectorStore({
      dimension: 4,
      embeddingProvider: new LocalEmbeddingProvider(),
    })
  })

  it('inserts and searches entries', async () => {
    await store.insert('TypeScript is a typed language', { type: 'fact', tags: ['programming'] })
    await store.insert('Python is great for data science', { type: 'fact', tags: ['programming'] })
    await store.insert('I love pizza', { type: 'preference', tags: ['food'] })

    const results = await store.search({ query: 'programming', limit: 5 })
    expect(results.length).toBeGreaterThanOrEqual(2)
  })

  it('filters by type and tags', async () => {
    await store.insert('like hiking', { type: 'preference', tags: ['outdoor'] })
    await store.insert('hiking is healthy', { type: 'fact', tags: ['health'] })

    const prefs = await store.search({ query: 'hiking', type: 'preference' })
    expect(prefs).toHaveLength(1)
    expect(prefs[0]!.metadata.type).toBe('preference')
  })

  it('deletes entries', async () => {
    const entry = await store.insert('test', { type: 'fact' })
    expect(store.count()).toBe(1)
    store.delete(entry.id)
    expect(store.count()).toBe(0)
  })
})

// ─── UserProfileStore ──────────────────────────────────────────────

describe('UserProfileStore', () => {
  let store: UserProfileStore

  beforeEach(async () => {
    store = new UserProfileStore({ dbPath: join(testDir, 'profiles.json') })
    await store.load()
  })

  afterEach(async () => { await store.save() })

  it('creates new profile on getOrCreate', () => {
    const profile = store.getOrCreate('user-1')
    expect(profile.userId).toBe('user-1')
    expect(profile.facts).toHaveLength(0)
  })

  it('adds facts with confidence', async () => {
    await store.addFact('user-1', { content: 'Loves TypeScript', category: 'preference', confidence: 0.9, source: 'chat' })
    const facts = store.getTopFacts('user-1')
    expect(facts).toHaveLength(1)
    expect(facts[0]!.content).toBe('Loves TypeScript')
  })

  it('generates summary', async () => {
    await store.addFact('user-2', { content: 'Expert in React', category: 'skill', confidence: 0.95, source: 'test' })
    await store.updatePreferences('user-2', { language: 'pt-BR', topics: ['typescript', 'react'] })
    const summary = store.generateSummary('user-2')
    expect(summary).toContain('React')
    expect(summary).toContain('pt-BR')
    expect(summary).toContain('typescript')
  })
})

// ─── SupermemoryClient ─────────────────────────────────────────────

describe('SupermemoryClient', () => {
  it('detects configured state', () => {
    const client = new SupermemoryClient({ apiKey: '' })
    expect(client.isConfigured()).toBe(false)

    const configured = new SupermemoryClient({ apiKey: 'sk-xxx' })
    expect(configured.isConfigured()).toBe(true)
  })

  it('uses env vars when available', () => {
    process.env.SUPERMEMORY_API_KEY = 'env-key'
    process.env.SUPERMEMORY_API_URL = 'https://custom.example.com'
    const client = new SupermemoryClient()
    expect(client.isConfigured()).toBe(true)
    delete process.env.SUPERMEMORY_API_KEY
    delete process.env.SUPERMEMORY_API_URL
  })
})

// ─── MemoryManager ─────────────────────────────────────────────────

describe('MemoryManager', () => {
  let manager: MemoryManager

  beforeEach(async () => {
    const dir = join(testDir, 'manager')
    manager = new MemoryManager({
      sessionDbPath: join(dir, 'sessions.json'),
      supermemory: { apiKey: '', baseUrl: '', timeout: 5000 },
    })
  })

  it('saves and recalls conversation memory', async () => {
    const entry = await manager.saveConversationMemory('sess-1', 'Important fact about the project', {
      userId: 'u1', type: 'semantic', tags: ['project'],
    })
    expect(entry.id).toBeDefined()
    expect(entry.content).toBe('Important fact about the project')

    const recall = await manager.recall('u1', 'project')
    expect(recall.relevantMemories.length).toBeGreaterThanOrEqual(1)
  })

  it('records user facts', async () => {
    await manager.recordUserFact('u2', 'Prefers concise answers', 'preference')
    const profile = manager.profiles.get('u2')
    expect(profile?.facts).toHaveLength(1)
    expect(profile?.facts[0]!.content).toBe('Prefers concise answers')
  })

  it('ingests conversation', async () => {
    await manager.ingestConversation('sess-3', [
      { role: 'user', content: 'Hello' },
      { role: 'assistant', content: 'Hi there!' },
    ], 'u3')

    const recall = await manager.recall('u3', 'Hello')
    expect(recall.relevantMemories.length).toBeGreaterThanOrEqual(1)
  })

  it('returns empty recall for unknown user', async () => {
    const recall = await manager.recall('unknown-user', 'anything')
    expect(recall.facts).toHaveLength(0)
    expect(recall.relevantMemories).toHaveLength(0)
  })
})
