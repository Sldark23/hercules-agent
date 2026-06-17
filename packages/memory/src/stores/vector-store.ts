import { randomUUID } from 'node:crypto'
import type { MemoryEntry, MemorySearchQuery, MemoryType } from '../types.js'
import type { EmbeddingProvider } from './embeddings.js'
import { createEmbeddingProvider } from './embeddings.js'

export interface VectorStoreConfig {
  dimension: number
  similarity: 'cosine' | 'dot' | 'euclidean'
  indexPath?: string
  embeddingProvider?: EmbeddingProvider
}

interface IndexEntry {
  id: string
  vector: number[]
  content: string
  metadata: {
    userId?: string
    sessionId?: string
    type: MemoryType
    tags: string[]
    source?: string
    importance: number
  }
  createdAt: Date
}

export class VectorStore {
  private entries: Map<string, IndexEntry> = new Map()
  private config: VectorStoreConfig
  private embedder: EmbeddingProvider

  constructor(config: Partial<VectorStoreConfig> = {}) {
    this.config = {
      dimension: config.dimension ?? 384,
      similarity: config.similarity ?? 'cosine',
    }
    this.embedder = config.embeddingProvider ?? createEmbeddingProvider()
  }

  async insert(content: string, metadata: {
    userId?: string
    sessionId?: string
    type: MemoryType
    tags?: string[]
    source?: string
    importance?: number
  }, embedding?: number[]): Promise<MemoryEntry> {
    const id = `mem-${randomUUID().slice(0, 12)}`
    const vec = embedding ?? await this.createEmbedding(content)

    const entry: IndexEntry = {
      id,
      vector: vec,
      content,
      metadata: {
        userId: metadata.userId,
        sessionId: metadata.sessionId,
        type: metadata.type,
        tags: metadata.tags ?? [],
        source: metadata.source,
        importance: metadata.importance ?? 1,
      },
      createdAt: new Date(),
    }

    this.entries.set(id, entry)

    return {
      id,
      content,
      embedding: vec,
      metadata: entry.metadata,
      createdAt: entry.createdAt,
    }
  }

  async insertBatch(items: Array<{
    content: string
    metadata: {
      userId?: string
      sessionId?: string
      type: MemoryType
      tags?: string[]
      importance?: number
    }
    embedding?: number[]
  }>): Promise<MemoryEntry[]> {
    const entries: MemoryEntry[] = []
    for (const item of items) {
      entries.push(await this.insert(item.content, item.metadata, item.embedding))
    }
    return entries
  }

  async search(query: MemorySearchQuery): Promise<MemoryEntry[]> {
    const queryVec = await this.createEmbedding(query.query)
    const results: Array<{ entry: IndexEntry; score: number }> = []

    for (const entry of this.entries.values()) {
      if (query.userId && entry.metadata.userId !== query.userId) continue
      if (query.type && entry.metadata.type !== query.type) continue
      if (query.tags && !query.tags.some(t => entry.metadata.tags.includes(t))) continue
      if (query.importance && entry.metadata.importance < query.importance) continue

      const score = this.similarity(queryVec, entry.vector)
      if (query.minScore && score < query.minScore) continue

      results.push({ entry, score })
    }

    results.sort((a, b) => b.score - a.score)
    const limit = query.limit ?? 10

    return results.slice(0, limit).map(r => ({
      id: r.entry.id,
      content: r.entry.content,
      metadata: r.entry.metadata,
      score: r.score,
      createdAt: r.entry.createdAt,
    }))
  }

  get(id: string): MemoryEntry | undefined {
    const entry = this.entries.get(id)
    if (!entry) return undefined
    return {
      id: entry.id,
      content: entry.content,
      metadata: entry.metadata,
      createdAt: entry.createdAt,
    }
  }

  delete(id: string): boolean {
    return this.entries.delete(id)
  }

  deleteBySession(sessionId: string): number {
    let count = 0
    for (const [id, entry] of this.entries) {
      if (entry.metadata.sessionId === sessionId) {
        this.entries.delete(id)
        count++
      }
    }
    return count
  }

  count(): number {
    return this.entries.size
  }

  clear(): void {
    this.entries.clear()
  }

  private async createEmbedding(text: string): Promise<number[]> {
    return this.embedder.embed(text)
  }

  getEmbedder(): EmbeddingProvider {
    return this.embedder
  }

  private fakeEmbedding(text: string): number[] {
    const dim = this.config.dimension
    const vec: number[] = new Array(dim)
    let hash = 0
    for (let i = 0; i < text.length; i++) {
      hash = ((hash << 5) - hash) + text.charCodeAt(i)
      hash |= 0
    }
    for (let i = 0; i < dim; i++) {
      vec[i] = Math.sin(hash * (i + 1)) * 0.5 + 0.5
    }
    return vec
  }

  private similarity(a: number[], b: number[]): number {
    if (this.config.similarity === 'cosine') {
      let dot = 0, na = 0, nb = 0
      for (let i = 0; i < a.length; i++) {
        dot += a[i]! * b[i]!
        na += a[i]! * a[i]!
        nb += b[i]! * b[i]!
      }
      const denom = Math.sqrt(na) * Math.sqrt(nb)
      return denom === 0 ? 0 : dot / denom
    }
    let dot = 0
    for (let i = 0; i < a.length; i++) dot += a[i]! * b[i]!
    return dot
  }
}
