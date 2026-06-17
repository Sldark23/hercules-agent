import { randomUUID } from 'node:crypto'
import { mkdir, writeFile, readFile } from 'node:fs/promises'
import { existsSync, createReadStream } from 'node:fs'
import { join, dirname } from 'node:path'
import type { SessionRecord, MessageRecord, SessionSearchResult } from '../types.js'

export interface SessionStoreConfig {
  dbPath: string
}

export class SessionStore {
  private sessions: Map<string, SessionRecord> = new Map()
  private messages: Map<string, MessageRecord[]> = new Map()
  private config: SessionStoreConfig
  private ready = false

  constructor(config: SessionStoreConfig) {
    this.config = config
  }

  async init(): Promise<void> {
    const dir = dirname(this.config.dbPath)
    if (!existsSync(dir)) await mkdir(dir, { recursive: true })

    if (existsSync(this.config.dbPath)) {
      try {
        const raw = await readFile(this.config.dbPath, 'utf-8')
        const data = JSON.parse(raw)
        if (data.sessions) {
          for (const [id, s] of Object.entries(data.sessions)) {
            this.sessions.set(id, s as SessionRecord)
          }
        }
        if (data.messages) {
          for (const [id, msgs] of Object.entries(data.messages)) {
            this.messages.set(id, msgs as MessageRecord[])
          }
        }
      } catch {}
    }
    this.ready = true
  }

  async saveSession(session: SessionRecord): Promise<void> {
    session.updatedAt = new Date()
    this.sessions.set(session.id, session)
    await this.persist()
  }

  getSession(id: string): SessionRecord | undefined {
    return this.sessions.get(id)
  }

  listSessions(userId?: string, limit = 50): SessionRecord[] {
    const all = Array.from(this.sessions.values())
    const filtered = userId ? all.filter(s => s.userId === userId) : all
    return filtered.sort((a, b) => b.updatedAt.getTime() - a.updatedAt.getTime()).slice(0, limit)
  }

  async addMessage(msg: MessageRecord): Promise<void> {
    const existing = this.messages.get(msg.sessionId) ?? []
    existing.push(msg)
    this.messages.set(msg.sessionId, existing)

    const session = this.sessions.get(msg.sessionId)
    if (session) {
      session.messageCount = existing.length
      session.tokenCount += msg.tokenCount
      session.updatedAt = new Date()
    }

    await this.persist()
  }

  getMessages(sessionId: string, limit = 100): MessageRecord[] {
    const msgs = this.messages.get(sessionId) ?? []
    return msgs.slice(-limit)
  }

  deleteSession(id: string): void {
    this.sessions.delete(id)
    this.messages.delete(id)
    this.persist()
  }

  async searchSessions(query: string, limit = 10): Promise<SessionSearchResult[]> {
    const results: SessionSearchResult[] = []
    const lower = query.toLowerCase()

    for (const [id, session] of this.sessions) {
      const msgs = this.messages.get(id) ?? []
      const allText = msgs.map(m => m.content).join(' ').toLowerCase()
      const titleText = session.title?.toLowerCase() ?? ''
      const tagText = session.tags.join(' ').toLowerCase()

      let relevance = 0
      if (titleText.includes(lower)) relevance += 3
      if (tagText.includes(lower)) relevance += 2
      relevance += (allText.split(lower).length - 1)
      if (relevance <= 0) continue

      const snippet = msgs.find(m => m.content.toLowerCase().includes(lower))
        ?.content.slice(0, 200) ?? allText.slice(0, 200)

      results.push({
        sessionId: id,
        snippet,
        relevance,
        title: session.title,
        timestamp: session.updatedAt,
      })
    }

    return results.sort((a, b) => b.relevance - a.relevance).slice(0, limit)
  }

  count(): { sessions: number; messages: number } {
    let totalMessages = 0
    for (const msgs of this.messages.values()) totalMessages += msgs.length
    return { sessions: this.sessions.size, messages: totalMessages }
  }

  async close(): Promise<void> {
    await this.persist()
    this.ready = false
  }

  private async persist(): Promise<void> {
    if (!this.ready) return
    const data = JSON.stringify({
      sessions: Object.fromEntries(this.sessions),
      messages: Object.fromEntries(this.messages),
    })
    await writeFile(this.config.dbPath, data, 'utf-8')
  }
}
