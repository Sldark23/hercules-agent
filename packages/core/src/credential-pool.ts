import type { Credential, ProviderId } from './types.js'

export interface CredentialPoolConfig {
  maxRetriesPerKey: number
  cooldownMinutes: number
  rotationStrategy: 'round-robin' | 'least-used' | 'priority'
}

export class CredentialPool {
  private credentials: Map<string, Credential> = new Map()
  private usageCount: Map<string, number> = new Map()
  private config: CredentialPoolConfig

  constructor(config: Partial<CredentialPoolConfig> = {}) {
    this.config = {
      maxRetriesPerKey: 3,
      cooldownMinutes: 5,
      rotationStrategy: 'round-robin',
      ...config,
    }
  }

  register(cred: Credential): void {
    this.credentials.set(cred.id, {
      ...cred,
      failureCount: 0,
      isActive: true,
    })
    this.usageCount.set(cred.id, 0)
  }

  registerBatch(creds: Credential[]): void {
    for (const c of creds) this.register(c)
  }

  getActive(providerId: ProviderId): Credential | undefined {
    const candidates = Array.from(this.credentials.values())
      .filter(c => c.providerId === providerId && c.isActive && !this.isOnCooldown(c))

    if (candidates.length === 0) return undefined

    return this.pickByStrategy(candidates)
  }

  getById(id: string): Credential | undefined {
    return this.credentials.get(id)
  }

  recordSuccess(id: string): void {
    const cred = this.credentials.get(id)
    if (!cred) return
    cred.failureCount = 0
    cred.cooldownUntil = undefined
    this.usageCount.set(id, (this.usageCount.get(id) ?? 0) + 1)
  }

  recordFailure(id: string): void {
    const cred = this.credentials.get(id)
    if (!cred) return
    cred.failureCount++
    this.usageCount.set(id, (this.usageCount.get(id) ?? 0) + 1)

    if (cred.failureCount >= this.config.maxRetriesPerKey) {
      cred.isActive = false
      cred.cooldownUntil = new Date(Date.now() + this.config.cooldownMinutes * 60_000)
    }
  }

  reactivate(id: string): void {
    const cred = this.credentials.get(id)
    if (!cred) return
    cred.isActive = true
    cred.failureCount = 0
    cred.cooldownUntil = undefined
  }

  hasAvailable(providerId: ProviderId): boolean {
    return Array.from(this.credentials.values())
      .some(c => c.providerId === providerId && c.isActive && !this.isOnCooldown(c))
  }

  all(): Credential[] {
    return Array.from(this.credentials.values())
  }

  reset(): void {
    this.credentials.clear()
    this.usageCount.clear()
  }

  private isOnCooldown(cred: Credential): boolean {
    if (!cred.cooldownUntil) return false
    return cred.cooldownUntil.getTime() > Date.now()
  }

  private pickByStrategy(candidates: Credential[]): Credential {
    switch (this.config.rotationStrategy) {
      case 'round-robin': {
        const sorted = [...candidates].sort(
          (a, b) => (this.usageCount.get(a.id) ?? 0) - (this.usageCount.get(b.id) ?? 0)
        )
        return sorted[0]!
      }
      case 'least-used': {
        const sorted = [...candidates].sort(
          (a, b) => (this.usageCount.get(a.id) ?? 0) - (this.usageCount.get(b.id) ?? 0)
        )
        return sorted[0]!
      }
      case 'priority': {
        return candidates[0]!
      }
    }
  }
}
