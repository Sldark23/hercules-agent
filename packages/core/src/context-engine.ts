import type { Message, ContextState, ContextConfig, CompressionEvent, TokenUsage } from './types.js'

export class ContextEngine {
  private sessions: Map<string, ContextState> = new Map()
  private config: ContextConfig

  constructor(config: Partial<ContextConfig> = {}) {
    this.config = {
      maxTokens: 200_000,
      compressionThreshold: 0.8,
      compressionTarget: 0.5,
      maxMessages: 500,
      ...config,
    }
  }

  init(sessionId: string): ContextState {
    const state: ContextState = {
      sessionId,
      messages: [],
      tokenBudget: this.config.maxTokens,
      usedTokens: 0,
      isCompressed: false,
      compressionHistory: [],
    }
    this.sessions.set(sessionId, state)
    return state
  }

  getState(sessionId: string): ContextState | undefined {
    return this.sessions.get(sessionId)
  }

  async addMessage(sessionId: string, message: Message): Promise<void> {
    const state = this.sessions.get(sessionId)
    if (!state) throw new Error(`Session ${sessionId} not found`)

    state.messages.push(message)
    state.usedTokens = this.estimateTokens(state.messages)

    if (this.needsCompression(state) || state.messages.length > this.config.maxMessages) {
      await this.compress(sessionId)
    }
  }

  async compress(sessionId: string): Promise<CompressionEvent> {
    const state = this.sessions.get(sessionId)
    if (!state) throw new Error(`Session ${sessionId} not found`)

    const originalTokens = state.usedTokens
    const targetTokens = Math.floor(this.config.maxTokens * this.config.compressionTarget)

    const olderMessages = state.messages.slice(0, -10)
    const recentMessages = state.messages.slice(-10)

    const summary = await this.summarizeMessages(olderMessages)
    const compressedTokens = this.estimateTokenCount(summary) + this.estimateTokens(recentMessages)

    state.messages = [
      {
        id: `compression-${Date.now()}`,
        role: 'system',
        content: `[Compressed summary of earlier conversation]: ${summary}`,
        createdAt: new Date(),
      },
      ...recentMessages,
    ]
    state.usedTokens = compressedTokens
    state.isCompressed = true

    const event: CompressionEvent = {
      timestamp: new Date(),
      originalTokens,
      compressedTokens,
      summary,
    }
    state.compressionHistory.push(event)
    return event
  }

  getWindow(sessionId: string, maxTokens?: number): Message[] {
    const state = this.sessions.get(sessionId)
    if (!state) throw new Error(`Session ${sessionId} not found`)

    const budget = maxTokens ?? this.config.maxTokens
    const messages: Message[] = []
    let total = 0

    for (const msg of [...state.messages].reverse()) {
      const tokens = this.tokenCount(msg.content)
      if (total + tokens > budget) break
      messages.unshift(msg)
      total += tokens
    }

    return messages
  }

  tokenCount(text: string): number {
    return this.estimateTokenCount(text)
  }

  usageSince(sessionId: string, since: Date): TokenUsage {
    const state = this.sessions.get(sessionId)
    if (!state) return { input: 0, output: 0 }

    let input = 0
    let output = 0
    for (const msg of state.messages) {
      if (msg.createdAt < since) continue
      const tokens = this.tokenCount(msg.content)
      if (msg.role === 'assistant') output += tokens
      else input += tokens
    }
    return { input, output }
  }

  destroy(sessionId: string): void {
    this.sessions.delete(sessionId)
  }

  private estimateTokens(messages: Message[]): number {
    return messages.reduce((sum, m) => sum + this.estimateTokenCount(m.content), 0)
  }

  private estimateTokenCount(text: string): number {
    return Math.ceil(text.length / 4)
  }

  private needsCompression(state: ContextState): boolean {
    return state.usedTokens > this.config.maxTokens * this.config.compressionThreshold
  }

  private async summarizeMessages(_messages: Message[]): Promise<string> {
    const count = _messages.length
    const topics = new Set<string>()
    let totalChars = 0

    for (const msg of _messages.slice(-20)) {
      totalChars += msg.content.length
      const words = msg.content.split(/\s+/).slice(0, 10)
      topics.add(words.join(' '))
    }

    return `[${count} messages, ~${totalChars} chars covering topics: ${Array.from(topics).slice(0, 5).join(', ')}]`
  }
}

export function estimateTokenCount(text: string): number {
  return Math.ceil(text.length / 4)
}
