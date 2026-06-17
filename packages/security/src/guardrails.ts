import type { GuardrailConfig, GuardrailResult, GuardrailRule } from './types.js'
import { SENSITIVE_DATA_PATTERNS, BLOCKED_PATTERNS } from './types.js'

const DEFAULT_RULES: GuardrailRule[] = [
  {
    name: 'block-rm-rf-root',
    description: 'Blocks destructive filesystem commands on root',
    severity: 'critical',
    pattern: /rm\s+-rf\s+\/$|rm\s+-rf\s+\/\s+/i,
    action: 'block',
  },
  {
    name: 'block-format-commands',
    description: 'Blocks disk format commands',
    severity: 'critical',
    pattern: /(?:mkfs\.|fdisk|parted|dd if=\/dev\/zero)/i,
    action: 'block',
  },
  {
    name: 'block-fork-bomb',
    description: 'Blocks fork bomb attempts',
    severity: 'critical',
    pattern: /:\(\)\s*\{/,
    action: 'block',
  },
  {
    name: 'flag-sensitive-data',
    description: 'Flag potential API keys and secrets in output',
    severity: 'high',
    pattern: (input: string) => SENSITIVE_DATA_PATTERNS.some(p => p.test(input)),
    action: 'flag',
    sanitize: (input: string) => {
      let sanitized = input
      for (const p of SENSITIVE_DATA_PATTERNS) {
        sanitized = sanitized.replace(p, '[REDACTED]')
      }
      return sanitized
    },
  },
  {
    name: 'block-dangerous-shell',
    description: 'Blocks dangerous shell patterns',
    severity: 'high',
    pattern: (input: string) => BLOCKED_PATTERNS.some(p => p.test(input)),
    action: 'block',
  },
]

export class GuardrailEngine {
  private config: GuardrailConfig
  private flagCount: Map<string, number> = new Map()

  constructor(config: Partial<GuardrailConfig> = {}) {
    this.config = {
      enabled: true,
      rules: DEFAULT_RULES,
      mode: 'blocking',
      maxFlagsBeforeBlock: 3,
      ...config,
    }
  }

  async check(input: string, context?: { userId?: string; sessionId?: string }): Promise<GuardrailResult> {
    if (!this.config.enabled) {
      return { action: 'allow', reason: 'Guardrails disabled', severity: 'low', matchedRules: [] }
    }

    const results: GuardrailResult[] = []

    for (const rule of this.config.rules) {
      try {
        let matched = false
        if (rule.pattern instanceof RegExp) {
          matched = rule.pattern.test(input)
        } else {
          matched = rule.pattern(input)
        }

        if (matched) {
          const sanitizedContent = rule.sanitize?.(input)
          results.push({
            action: rule.action,
            reason: `Rule "${rule.name}": ${rule.description}`,
            severity: rule.severity,
            sanitizedContent,
            matchedRules: [rule.name],
          })
        }
      } catch {
        // rule check failed silently
      }
    }

    if (results.length === 0) {
      return { action: 'allow', reason: 'No rules matched', severity: 'low', matchedRules: [] }
    }

    const blocks = results.filter(r => r.action === 'block')
    const flags = results.filter(r => r.action === 'flag')

    if (blocks.length > 0) {
      if (this.config.mode === 'monitoring') {
        flags.push(...blocks.map(b => ({ ...b, action: 'flag' as const })))
      } else {
        return {
          action: 'block',
          reason: blocks.map(b => b.reason).join('; '),
          severity: 'critical',
          matchedRules: blocks.map(b => b.matchedRules).flat(),
        }
      }
    }

    if (flags.length > 0) {
      const key = context?.userId ?? context?.sessionId ?? 'global'
      const count = (this.flagCount.get(key) ?? 0) + 1
      this.flagCount.set(key, count)

      if (count >= this.config.maxFlagsBeforeBlock && this.config.mode === 'blocking') {
        return {
          action: 'block',
          reason: `Exceeded max flags (${this.config.maxFlagsBeforeBlock}) with sensitive data`,
          severity: 'high',
          matchedRules: flags.map(f => f.matchedRules).flat(),
        }
      }

      const sanitized = flags.find(f => f.sanitizedContent)?.sanitizedContent
      return {
        action: 'sanitize',
        reason: flags.map(f => f.reason).join('; '),
        severity: 'medium',
        sanitizedContent: sanitized ?? input,
        matchedRules: flags.map(f => f.matchedRules).flat(),
      }
    }

    return results[0]!
  }

  addRule(rule: GuardrailRule): void {
    this.config.rules.push(rule)
  }

  removeRule(name: string): boolean {
    const idx = this.config.rules.findIndex(r => r.name === name)
    if (idx === -1) return false
    this.config.rules.splice(idx, 1)
    return true
  }

  getRules(): GuardrailRule[] {
    return [...this.config.rules]
  }

  setMode(mode: 'blocking' | 'monitoring'): void {
    this.config.mode = mode
  }

  resetFlags(key?: string): void {
    if (key) this.flagCount.delete(key)
    else this.flagCount.clear()
  }

  getMetrics(): { totalRules: number; flagCounts: Record<string, number> } {
    return {
      totalRules: this.config.rules.length,
      flagCounts: Object.fromEntries(this.flagCount),
    }
  }
}
