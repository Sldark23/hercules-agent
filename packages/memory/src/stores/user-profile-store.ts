import { randomUUID } from 'node:crypto'
import type { UserProfile, UserPreferences, UserFact } from '../types.js'

export interface UserProfileStoreConfig {
  dbPath: string
}

export class UserProfileStore {
  private profiles: Map<string, UserProfile> = new Map()
  private config: UserProfileStoreConfig

  constructor(config: UserProfileStoreConfig) {
    this.config = config
  }

  async load(): Promise<void> {
    const { readFile, existsSync } = await import('node:fs')
    if (existsSync(this.config.dbPath)) {
      try {
        const raw = await import('node:fs/promises').then(fs => fs.readFile(this.config.dbPath, 'utf-8'))
        const data = JSON.parse(raw)
        for (const [id, p] of Object.entries(data)) {
          this.profiles.set(id, p as UserProfile)
        }
      } catch {}
    }
  }

  getOrCreate(userId: string): UserProfile {
    const existing = this.profiles.get(userId)
    if (existing) return existing

    const profile: UserProfile = {
      userId,
      preferences: {
        topics: [],
        avoidTopics: [],
        custom: {},
      },
      facts: [],
      interactionCount: 0,
      lastActive: new Date(),
      createdAt: new Date(),
    }
    this.profiles.set(userId, profile)
    return profile
  }

  get(userId: string): UserProfile | undefined {
    return this.profiles.get(userId)
  }

  async updatePreferences(userId: string, prefs: Partial<UserPreferences>): Promise<UserProfile> {
    const profile = this.getOrCreate(userId)
    profile.preferences = { ...profile.preferences, ...prefs }
    await this.save()
    return profile
  }

  async addFact(userId: string, fact: Omit<UserFact, 'timestamp'>): Promise<UserFact> {
    const profile = this.getOrCreate(userId)
    const newFact: UserFact = {
      ...fact,
      timestamp: new Date(),
    }
    profile.facts.push(newFact)
    await this.save()
    return newFact
  }

  async recordInteraction(userId: string): Promise<void> {
    const profile = this.getOrCreate(userId)
    profile.interactionCount++
    profile.lastActive = new Date()
    await this.save()
  }

  getTopFacts(userId: string, limit = 10): UserFact[] {
    const profile = this.profiles.get(userId)
    if (!profile) return []
    return [...profile.facts]
      .sort((a, b) => b.confidence - a.confidence)
      .slice(0, limit)
  }

  generateSummary(userId: string): string {
    const profile = this.profiles.get(userId)
    if (!profile) return ''

    const parts: string[] = []
    if (profile.facts.length > 0) {
      const top = this.getTopFacts(userId, 5)
      parts.push('Known facts:')
      for (const f of top) {
        parts.push(`- [${f.category}] ${f.content}`)
      }
    }

    if (profile.preferences.topics.length > 0) {
      parts.push(`Interested in: ${profile.preferences.topics.join(', ')}`)
    }
    if (profile.preferences.language) {
      parts.push(`Language: ${profile.preferences.language}`)
    }
    if (profile.preferences.tone) {
      parts.push(`Preferred tone: ${profile.preferences.tone}`)
    }

    parts.push(`Interactions: ${profile.interactionCount}`)
    return parts.join('\n')
  }

  async save(): Promise<void> {
    const { writeFile, mkdir } = await import('node:fs/promises')
    const { dirname } = await import('node:path')
    const { existsSync } = await import('node:fs')
    const dir = dirname(this.config.dbPath)
    if (!existsSync(dir)) await mkdir(dir, { recursive: true })

    await writeFile(this.config.dbPath, JSON.stringify(Object.fromEntries(this.profiles)), 'utf-8')
  }

  count(): number {
    return this.profiles.size
  }
}
