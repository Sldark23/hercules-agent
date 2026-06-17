import { z } from 'zod'

export type GuardrailAction = 'allow' | 'block' | 'flag' | 'sanitize'

export interface GuardrailResult {
  action: GuardrailAction
  reason: string
  severity: 'low' | 'medium' | 'high' | 'critical'
  sanitizedContent?: string
  matchedRules: string[]
}

export interface GuardrailRule {
  name: string
  description: string
  severity: 'low' | 'medium' | 'high' | 'critical'
  pattern: RegExp | ((input: string) => boolean)
  action: GuardrailAction
  sanitize?: (input: string) => string
}

export interface GuardrailConfig {
  enabled: boolean
  rules: GuardrailRule[]
  mode: 'blocking' | 'monitoring'
  maxFlagsBeforeBlock: number
}

export interface RateLimitConfig {
  windowMs: number
  maxRequests: number
  type: 'ip' | 'userId' | 'apiKey'
}

export interface RateLimitState {
  key: string
  count: number
  windowStart: number
  blocked: boolean
  blockedUntil?: number
}

export interface PermissionScope {
  resource: string
  action: 'read' | 'write' | 'execute' | 'admin'
}

export interface Permission {
  id: string
  role: string
  scopes: PermissionScope[]
  constraints?: Record<string, unknown>
}

export interface ApprovalRequest {
  id: string
  toolCallId: string
  toolName: string
  arguments: Record<string, unknown>
  userId?: string
  sessionId: string
  reason: string
  requestedAt: Date
  status: 'pending' | 'approved' | 'rejected'
  decidedBy?: string
  decidedAt?: Date
}

export const ALLOWED_ENV_PATTERNS = [
  /^HOME$/,
  /^USER$/,
  /^PATH$/,
  /^NODE_ENV$/,
  /^SHELL$/,
  /^LANG$/,
  /^LC_.*/,
  /^TZ$/,
]

export const BLOCKED_PATTERNS = [
  /rm\s+-rf\s+\//,
  /mkfs\./,
  /dd\s+if=\/dev\/zero/,
  /:\(\)\s*\{/,
  />\/dev\/sda/,
]

export const SENSITIVE_DATA_PATTERNS = [
  /(?:(?:sk|pk)_[a-zA-Z0-9]{20,})/,
  /(?:sk-proj-[a-zA-Z0-9]{20,})/,
  /(?:-----BEGIN (?:RSA |EC )?PRIVATE KEY-----)/,
  /(?:ghp_\w{36})/,
  /(?:gho_\w{36})/,
  /(?:ghu_\w{36})/,
  /(?:ghs_\w{36})/,
  /(?:ghr_\w{36})/,
  /(?:xox[baprs]-[a-zA-Z0-9-]{10,})/,
]
