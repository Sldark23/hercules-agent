import type {
  SupermemoryDocument, SupermemorySearchResult,
  SupermemoryUserProfile, SupermemoryFact,
} from '../types.js'

export interface SupermemoryClientConfig {
  apiKey: string
  baseUrl: string
  timeout: number
}

export class SupermemoryClient {
  private config: SupermemoryClientConfig

  constructor(config: Partial<SupermemoryClientConfig> = {}) {
    this.config = {
      apiKey: config.apiKey ?? process.env.SUPERMEMORY_API_KEY ?? '',
      baseUrl: config.baseUrl ?? process.env.SUPERMEMORY_API_URL ?? 'https://api.supermemory.ai/v3',
      timeout: config.timeout ?? 15_000,
    }
  }

  isConfigured(): boolean {
    return !!this.config.apiKey
  }

  // ─── Documents ─────────────────────────────────────────────────

  async addDocument(doc: SupermemoryDocument): Promise<{ id: string }> {
    return this.post('/documents', doc)
  }

  async addDocuments(docs: SupermemoryDocument[]): Promise<{ ids: string[] }> {
    return this.post('/documents/batch', { documents: docs })
  }

  async deleteDocument(id: string): Promise<void> {
    return this.delete(`/documents/${id}`)
  }

  async getDocument(id: string): Promise<SupermemoryDocument> {
    return this.get(`/documents/${id}`)
  }

  // ─── Search ─────────────────────────────────────────────────────

  async search(query: string, options?: {
    userId?: string
    limit?: number
    type?: string
    tags?: string[]
    similarityThreshold?: number
  }): Promise<SupermemorySearchResult[]> {
    return this.post('/search', { query, ...options })
  }

  async hybridSearch(query: string, options?: {
    userId?: string
    limit?: number
    type?: string
  }): Promise<SupermemorySearchResult[]> {
    return this.post('/search/hybrid', { query, ...options })
  }

  // ─── User Profile ───────────────────────────────────────────────

  async getUserProfile(userId: string): Promise<SupermemoryUserProfile> {
    return this.get(`/users/${userId}/profile`)
  }

  async updateUserProfile(userId: string, data: {
    facts?: Omit<SupermemoryFact, 'id'>[]
    preferences?: Record<string, unknown>
    summary?: string
  }): Promise<SupermemoryUserProfile> {
    return this.put(`/users/${userId}/profile`, data)
  }

  async addFact(userId: string, fact: Omit<SupermemoryFact, 'id'>): Promise<SupermemoryFact> {
    return this.post(`/users/${userId}/facts`, fact)
  }

  // ─── Memories ───────────────────────────────────────────────────

  async saveMemory(data: {
    content: string
    userId?: string
    tags?: string[]
    type?: string
    metadata?: Record<string, unknown>
  }): Promise<{ id: string }> {
    return this.post('/memories', data)
  }

  async recallMemories(userId: string, query?: string): Promise<SupermemorySearchResult[]> {
    return this.post('/memories/recall', { userId, query })
  }

  async forgetMemory(id: string): Promise<void> {
    return this.delete(`/memories/${id}`)
  }

  // ─── Health ─────────────────────────────────────────────────────

  async health(): Promise<{ status: string; version: string }> {
    return this.get('/health')
  }

  // ─── Internal ───────────────────────────────────────────────────

  private async get<T>(path: string): Promise<T> {
    return this.request('GET', path)
  }

  private async post<T>(path: string, body?: unknown): Promise<T> {
    return this.request('POST', path, body)
  }

  private async put<T>(path: string, body?: unknown): Promise<T> {
    return this.request('PUT', path, body)
  }

  private async delete<T>(path: string): Promise<T> {
    return this.request('DELETE', path)
  }

  private async request<T>(method: string, path: string, body?: unknown): Promise<T> {
    const url = `${this.config.baseUrl}${path}`
    const headers: Record<string, string> = {
      'Content-Type': 'application/json',
    }
    if (this.config.apiKey) {
      headers['Authorization'] = `Bearer ${this.config.apiKey}`
    }

    const controller = new AbortController()
    const timer = setTimeout(() => controller.abort(), this.config.timeout)

    try {
      const res = await fetch(url, {
        method,
        headers,
        body: body ? JSON.stringify(body) : undefined,
        signal: controller.signal,
      })

      if (!res.ok) {
        const text = await res.text().catch(() => '')
        throw new Error(`Supermemory API ${res.status}: ${text || res.statusText}`)
      }

      if (res.status === 204) return undefined as T
      return res.json() as Promise<T>
    } finally {
      clearTimeout(timer)
    }
  }
}
