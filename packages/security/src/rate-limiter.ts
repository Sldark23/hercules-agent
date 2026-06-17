import type { RateLimitConfig, RateLimitState } from './types.js'
import { randomUUID } from 'node:crypto'

export class RateLimiter {
  private states: Map<string, RateLimitState> = new Map()
  private configs: Map<string, RateLimitConfig> = new Map()
  private cleanupTimer: ReturnType<typeof setInterval> | null = null

  constructor() {
    this.startCleanup()
  }

  defineLimit(name: string, config: RateLimitConfig): void {
    this.configs.set(name, config)
  }

  check(name: string, key: string): { allowed: boolean; remaining: number; resetMs: number } {
    const config = this.configs.get(name)
    if (!config) return { allowed: true, remaining: Infinity, resetMs: 0 }

    const stateKey = `${name}:${key}`
    const now = Date.now()
    let state = this.states.get(stateKey)

    if (!state || (now - state.windowStart) >= config.windowMs) {
      state = { key: stateKey, count: 0, windowStart: now, blocked: false }
      this.states.set(stateKey, state)
    }

    if (state.blocked) {
      if (state.blockedUntil && now >= state.blockedUntil) {
        state.blocked = false
        state.count = 0
        state.windowStart = now
        state.blockedUntil = undefined
      } else {
        const resetMs = (state.blockedUntil ?? now + config.windowMs) - now
        return { allowed: false, remaining: 0, resetMs }
      }
    }

    state.count++

    if (state.count > config.maxRequests) {
      state.blocked = true
      state.blockedUntil = now + config.windowMs
      return { allowed: false, remaining: 0, resetMs: config.windowMs }
    }

    const remaining = config.maxRequests - state.count
    const resetMs = (state.windowStart + config.windowMs) - now

    return { allowed: true, remaining, resetMs }
  }

  reset(name?: string, key?: string): void {
    if (name && key) {
      this.states.delete(`${name}:${key}`)
    } else if (name) {
      for (const k of this.states.keys()) {
        if (k.startsWith(`${name}:`)) this.states.delete(k)
      }
    } else {
      this.states.clear()
    }
  }

  getActiveLimits(): number {
    return this.states.size
  }

  destroy(): void {
    if (this.cleanupTimer) {
      clearInterval(this.cleanupTimer)
      this.cleanupTimer = null
    }
    this.states.clear()
    this.configs.clear()
  }

  private startCleanup(): void {
    this.cleanupTimer = setInterval(() => {
      const now = Date.now()
      for (const [key, state] of this.states) {
        if (!state.blocked && (now - state.windowStart) >= 60000) {
          this.states.delete(key)
        }
      }
    }, 60000)
  }
}
