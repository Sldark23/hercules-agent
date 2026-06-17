import { z } from 'zod'

// ─── Session Store ─────────────────────────────────────────────────

export interface SessionRecord {
  id: string
  userId?: string
  platform?: string
  title?: string
  messageCount: number
  tokenCount: number
  modelId?: string
  tags: string[]
  createdAt: Date
  updatedAt: Date
  metadata?: Record<string, unknown>
}

export interface MessageRecord {
  id: string
  sessionId: string
  role: 'user' | 'assistant' | 'system' | 'tool'
  content: string
  tokenCount: number
  toolName?: string
  timestamp: Date
}

export interface SessionSearchResult {
  sessionId: string
  snippet: string
  relevance: number
  title?: string
  timestamp: Date
}

// ─── Vector Memory ─────────────────────────────────────────────────

export interface MemoryEntry {
  id: string
  content: string
  embedding?: number[]
  metadata: MemoryMetadata
  score?: number
  createdAt: Date
}

export interface MemoryMetadata {
  userId?: string
  sessionId?: string
  type: MemoryType
  tags: string[]
  source?: string
  importance: number
  ttl?: number
}

export type MemoryType = 'fact' | 'concept' | 'preference' | 'procedure' | 'episodic' | 'semantic'

export interface MemorySearchQuery {
  query: string
  userId?: string
  type?: MemoryType
  tags?: string[]
  limit?: number
  minScore?: number
  importance?: number
}

// ─── SuperMemory API ───────────────────────────────────────────────

export const SupermemoryDocumentSchema = z.object({
  id: z.string().optional(),
  title: z.string().optional(),
  content: z.string().min(1),
  url: z.string().optional(),
  type: z.enum(['text', 'webpage', 'document', 'conversation', 'code']).optional().default('text'),
  userId: z.string().optional(),
  tags: z.array(z.string()).optional(),
  metadata: z.record(z.unknown()).optional(),
})

export type SupermemoryDocument = z.infer<typeof SupermemoryDocumentSchema>

export interface SupermemorySearchResult {
  id: string
  content: string
  title?: string
  url?: string
  score: number
  type: string
  tags: string[]
  metadata?: Record<string, unknown>
}

export interface SupermemoryUserProfile {
  userId: string
  facts: SupermemoryFact[]
  preferences: Record<string, unknown>
  summary: string
}

export interface SupermemoryFact {
  id: string
  content: string
  category: string
  confidence: number
  source?: string
  timestamp: string
}

import type { SupermemoryClientConfig } from './supermemory/client.js'

// ─── Memory Manager ────────────────────────────────────────────────

export interface MemoryManagerConfig {
  sessionDbPath: string
  supermemory: SupermemoryClientConfig
  vectorDimension: number
  defaultImportance: number
  recallLimit: number
}

export interface RecallContext {
  facts: string[]
  preferences: Record<string, unknown>
  userSummary: string
  recentSessions: string[]
  relevantMemories: MemoryEntry[]
}

// ─── User Profile ──────────────────────────────────────────────────

export interface UserProfile {
  userId: string
  name?: string
  preferences: UserPreferences
  facts: UserFact[]
  interactionCount: number
  lastActive: Date
  createdAt: Date
}

export interface UserPreferences {
  language?: string
  tone?: string
  responseStyle?: string
  topics: string[]
  avoidTopics: string[]
  custom: Record<string, unknown>
}

export interface UserFact {
  content: string
  category: 'personal' | 'professional' | 'preference' | 'skill' | 'knowledge' | 'behavior'
  confidence: number
  source: string
  timestamp: Date
}
