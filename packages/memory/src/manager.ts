import { SessionStore } from './stores/session-store.js'
import { VectorStore } from './stores/vector-store.js'
import { UserProfileStore } from './stores/user-profile-store.js'
import { SupermemoryClient } from './supermemory/client.js'
import type {
  MemoryManagerConfig, RecallContext, MemoryEntry,
  MemoryType, MemorySearchQuery,
} from './types.js'

export class MemoryManager {
  readonly sessions: SessionStore
  readonly vectors: VectorStore
  readonly profiles: UserProfileStore
  readonly supermemory: SupermemoryClient
  private config: MemoryManagerConfig

  constructor(config: Partial<MemoryManagerConfig> = {}) {
    this.config = {
      sessionDbPath: config.sessionDbPath ?? './data/sessions.json',
      supermemory: config.supermemory ?? { apiKey: '', baseUrl: 'https://api.supermemory.ai/v3', timeout: 15_000 },
      vectorDimension: config.vectorDimension ?? 384,
      defaultImportance: config.defaultImportance ?? 3,
      recallLimit: config.recallLimit ?? 10,
    }

    this.sessions = new SessionStore({ dbPath: this.config.sessionDbPath })
    this.vectors = new VectorStore({ dimension: this.config.vectorDimension })
    this.profiles = new UserProfileStore({ dbPath: this.config.sessionDbPath.replace('sessions', 'profiles') })
    this.supermemory = new SupermemoryClient(this.config.supermemory)
  }

  async initialize(): Promise<void> {
    await this.sessions.init()
    await this.profiles.load()
  }

  async saveConversationMemory(
    sessionId: string,
    content: string,
    options?: {
      userId?: string
      type?: MemoryType
      tags?: string[]
      importance?: number
    }
  ): Promise<MemoryEntry> {
    const entry = await this.vectors.insert(content, {
      userId: options?.userId,
      sessionId,
      type: options?.type ?? 'episodic',
      tags: options?.tags ?? [],
      importance: options?.importance ?? this.config.defaultImportance,
    })

    if (this.supermemory.isConfigured()) {
      this.supermemory.saveMemory({
        content,
        userId: options?.userId,
        tags: options?.tags,
        type: options?.type,
        metadata: { sessionId },
      }).catch(() => {})
    }

    return entry
  }

  async recall(userId: string, query: string): Promise<RecallContext> {
    const profile = this.profiles.get(userId)
    const recentSessions = this.sessions.listSessions(userId, 5)

    const localResults = await this.vectors.search({
      query,
      userId,
      limit: this.config.recallLimit,
    })

    let supermemoryResults: Array<{ id: string; content: string; score: number }> = []

    if (this.supermemory.isConfigured()) {
      try {
        const results = await this.supermemory.search(query, { userId, limit: 5 })
        supermemoryResults = results.map(r => ({
          id: r.id,
          content: r.content,
          score: r.score,
        }))
      } catch {}
    }

    const facts = profile
      ? this.profiles.getTopFacts(userId, 5).map(f => `[${f.category}] ${f.content}`)
      : []

    const userSummary = profile
      ? this.profiles.generateSummary(userId)
      : ''

    const mappedSupermemory: MemoryEntry[] = supermemoryResults
      .filter(sr => !localResults.find(lr => lr.content === sr.content))
      .map(sr => ({
        id: sr.id,
        content: sr.content,
        metadata: { userId, type: 'semantic' as MemoryType, tags: [], importance: 3 },
        score: sr.score,
        createdAt: new Date(),
      }))

    const relevantMemories = [...localResults, ...mappedSupermemory]

    return {
      facts,
      preferences: profile?.preferences?.custom ?? {},
      userSummary,
      recentSessions: recentSessions.map(s => s.id),
      relevantMemories: relevantMemories.slice(0, this.config.recallLimit),
    }
  }

  async ingestConversation(
    sessionId: string,
    messages: Array<{ role: string; content: string }>,
    userId?: string
  ): Promise<void> {
    const fullText = messages.map(m => `[${m.role}] ${m.content}`).join('\n')

    await this.saveConversationMemory(sessionId, fullText, {
      userId,
      type: 'episodic',
      tags: ['conversation'],
    })

    if (userId && this.supermemory.isConfigured()) {
      this.supermemory.addDocument({
        content: fullText,
        type: 'conversation',
        userId,
        tags: ['conversation', `session:${sessionId}`],
        metadata: { sessionId, messageCount: messages.length },
      }).catch(() => {})
    }
  }

  async recordUserFact(
    userId: string,
    fact: string,
    category: 'personal' | 'professional' | 'preference' | 'skill' | 'knowledge' | 'behavior',
    confidence = 0.7
  ): Promise<void> {
    await this.profiles.addFact(userId, { content: fact, category, confidence, source: 'agent' })
    await this.vectors.insert(fact, {
      userId,
      type: 'fact',
      tags: [category],
      importance: 5,
    })

    if (this.supermemory.isConfigured()) {
      this.supermemory.addFact(userId, {
        content: fact,
        category,
        confidence,
        source: 'agent',
        timestamp: new Date().toISOString(),
      }).catch(() => {})
    }
  }

  async search(input: MemorySearchQuery): Promise<MemoryEntry[]> {
    const local = await this.vectors.search(input)

    if (this.supermemory.isConfigured() && input.userId) {
      try {
        const remote = await this.supermemory.search(input.query, {
          userId: input.userId,
          limit: input.limit,
        })
        const remoteEntries: MemoryEntry[] = remote.map(r => ({
          id: r.id,
          content: r.content,
          metadata: {
            userId: input.userId,
            type: 'semantic',
            tags: r.tags,
            importance: 3,
          },
          score: r.score,
          createdAt: new Date(),
        }))
        return [...local, ...remoteEntries.filter(r => !local.find(l => l.content === r.content))]
      } catch {}
    }

    return local
  }

  async close(): Promise<void> {
    await this.sessions.close()
    await this.profiles.save()
  }
}
