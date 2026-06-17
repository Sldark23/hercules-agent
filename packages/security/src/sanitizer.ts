import { ALLOWED_ENV_PATTERNS, SENSITIVE_DATA_PATTERNS } from './types.js'

export class InputSanitizer {
  sanitizeEnvVar(name: string): string | null {
    if (ALLOWED_ENV_PATTERNS.some(p => p.test(name))) return name
    return null
  }

  sanitizePath(input: string): string {
    return input
      .replace(/\.\.\//g, '')
      .replace(/\.\.\\/g, '')
      .replace(/\0/g, '')
      .replace(/[<>|]/g, '')
  }

  sanitizeCommand(input: string): string {
    return input
      .replace(/\$\(.*?\)/g, '[BLOCKED_SUBSHELL]')
      .replace(/`.*?`/g, '[BLOCKED_SUBSHELL]')
      .replace(/;\s*;/g, ';')
      .replace(/\|\|/g, '')
      .replace(/&&/g, '')
  }

  redactSecrets(input: string): string {
    let sanitized = input
    for (const pattern of SENSITIVE_DATA_PATTERNS) {
      sanitized = sanitized.replace(pattern, '[REDACTED]')
    }
    return sanitized
  }

  sanitizeJsonInput(input: unknown): unknown {
    if (typeof input === 'string') {
      const trimmed = input.trim()
      if (trimmed.length > 1_000_000) return trimmed.slice(0, 1_000_000)
      return trimmed
    }
    if (typeof input === 'object' && input !== null) {
      const obj = input as Record<string, unknown>
      for (const key of Object.keys(obj)) {
        if (['password', 'secret', 'token', 'apiKey', 'api_key', 'apikey', 'authorization'].includes(key.toLowerCase())) {
          obj[key] = '[REDACTED]'
        } else {
          obj[key] = this.sanitizeJsonInput(obj[key])
        }
      }
    }
    return input
  }
}
