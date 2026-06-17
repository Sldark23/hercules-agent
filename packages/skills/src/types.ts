import { z } from 'zod'
import type { SkillInjection } from '@hercules/core'

// ─── Manifest ────────────────────────────────────────────────────

export type SkillTriggerEvent =
  | 'agent:before_turn'
  | 'agent:after_turn'
  | 'agent:before_message'
  | 'agent:after_message'
  | 'session:before_create'
  | 'session:after_create'
  | 'startup:after'

export interface SkillTrigger {
  event: SkillTriggerEvent
  pattern?: string
  keywords?: string[]
}

export const SkillTriggerSchema = z.object({
  event: z.enum([
    'agent:before_turn', 'agent:after_turn',
    'agent:before_message', 'agent:after_message',
    'session:before_create', 'session:after_create',
    'startup:after',
  ]),
  pattern: z.string().optional(),
  keywords: z.array(z.string()).optional(),
})

export const SkillManifestSchema = z.object({
  name: z.string().min(1).max(64),
  version: z.string().regex(/^\d+\.\d+\.\d+$/, 'Must be semver'),
  description: z.string().default(''),
  author: z.string().optional(),
  tools: z.array(z.string()).default([]),
  hooks: z.array(z.string()).default([]),
  triggers: z.array(SkillTriggerSchema).default([]),
  prompt: z.string().default(''),
  priority: z.number().int().min(-100).max(100).default(0),
  requires: z.array(z.string()).default([]),
  config: z.record(z.unknown()).optional(),
})

export type SkillManifest = z.infer<typeof SkillManifestSchema>

// ─── Runtime ─────────────────────────────────────────────────────

export type SkillState = 'inactive' | 'active' | 'error' | 'disabled'

export interface SkillInstance {
  id: string
  manifest: SkillManifest
  state: SkillState
  path: string
  error?: string
  loadedAt: Date
}

// ─── SkillSandbox ────────────────────────────────────────────────

export interface SkillSandboxConfig {
  allowedTools: string[]
  allowedHooks: string[]
  skillConfig: Record<string, unknown>
  sandboxId: string
}

export interface SkillSandbox {
  id: string
  skillName: string
  config: SkillSandboxConfig
  isToolAllowed(name: string): boolean
  isHookAllowed(name: string): boolean
}

// ─── Engine ──────────────────────────────────────────────────────

export interface SkillsEngineConfig {
  skillsDir: string
  autoActivateOnStartup: boolean
  maxActiveSkills: number
  conflictResolution: 'priority' | 'last_wins' | 'error'
}

export interface SkillEvaluationResult {
  shouldActivate: boolean
  confidence: number
  matchedTriggers: SkillTrigger[]
}

export interface SkillsActiveSet {
  active: SkillInstance[]
  injections: SkillInjection[]
  timestamp: Date
}
