import { randomUUID } from 'node:crypto'
import type { AgentProfile, SwarmAgent, AgentCapability, AgentState } from './types.js'

export class AgentRegistry {
  private agents: Map<string, SwarmAgent> = new Map()

  register(profile: AgentProfile): SwarmAgent {
    const id = profile.id || randomUUID()
    if (this.agents.has(id)) {
      throw new Error(`Agent "${id}" is already registered`)
    }

    const agent: SwarmAgent = {
      profile: { ...profile, id },
      state: 'idle',
      totalTurns: 0,
      errorCount: 0,
    }

    this.agents.set(id, agent)
    return agent
  }

  get(id: string): SwarmAgent | undefined {
    return this.agents.get(id)
  }

  has(id: string): boolean {
    return this.agents.has(id)
  }

  remove(id: string): boolean {
    return this.agents.delete(id)
  }

  list(filter?: { state?: AgentState; capability?: AgentCapability }): SwarmAgent[] {
    let results = Array.from(this.agents.values())

    if (filter?.state) {
      results = results.filter(a => a.state === filter.state)
    }
    if (filter?.capability) {
      results = results.filter(a =>
        a.profile.capabilities.some(c => c.toLowerCase() === filter.capability!.toLowerCase())
      )
    }

    return results
  }

  updateState(id: string, state: AgentState): SwarmAgent {
    const agent = this.agents.get(id)
    if (!agent) throw new Error(`Agent "${id}" not found`)

    agent.state = state
    if (state === 'busy') agent.lastActiveAt = new Date()
    return agent
  }

  recordTurn(id: string): void {
    const agent = this.agents.get(id)
    if (agent) agent.totalTurns++
  }

  recordError(id: string): void {
    const agent = this.agents.get(id)
    if (agent) agent.errorCount++
  }

  findBestMatch(capabilities: AgentCapability[], requiredCapabilities: AgentCapability[]): SwarmAgent | undefined {
    const available = this.list({ state: 'idle' })
    if (available.length === 0) return undefined

    let best: SwarmAgent | undefined
    let bestScore = -1

    for (const agent of available) {
      let score = 0
      for (const req of requiredCapabilities) {
        if (agent.profile.capabilities.some(c => c.toLowerCase() === req.toLowerCase())) {
          score++
        }
      }
      if (agent.profile.weight) score *= agent.profile.weight

      if (score > bestScore) {
        bestScore = score
        best = agent
      }
    }

    return best
  }

  count(): number {
    return this.agents.size
  }

  clear(): void {
    this.agents.clear()
  }
}
