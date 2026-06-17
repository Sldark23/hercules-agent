import { randomUUID } from 'node:crypto'
import type { ChannelAdapter, ChannelMessage, ChannelEventHandler, OutboundMessage } from '../types.js'

export class SlackAdapter implements ChannelAdapter {
  readonly name: string
  readonly type = 'slack'
  private token: string
  private signingSecret?: string
  private handlers: ChannelEventHandler[] = []
  private running = false

  constructor(name: string, token: string, signingSecret?: string) {
    this.name = name
    this.token = token
    this.signingSecret = signingSecret
  }

  async start(): Promise<void> {
    if (this.running) return
    this.running = true
    console.log(`[slack:${this.name}] Ready`)

    try {
      const res = await fetch('https://slack.com/api/conversations.list', {
        headers: { Authorization: `Bearer ${this.token}` },
      })
      const data = (await res.json()) as Record<string, unknown>
      if (data.ok) {
        const channels = data.channels as Array<Record<string, unknown>> ?? []
        console.log(`[slack:${this.name}] Found ${channels.length} accessible channels`)
      }
    } catch {}
  }

  async stop(): Promise<void> {
    this.running = false
    console.log(`[slack:${this.name}] Stopped`)
  }

  async send(msg: OutboundMessage): Promise<string> {
    const body: Record<string, unknown> = {
      channel: msg.channelId,
      text: msg.text,
      mrkdwn: msg.parseMode === 'markdown' || msg.parseMode !== 'html',
    }
    if (msg.threadId) body.thread_ts = msg.threadId

    const res = await fetch('https://slack.com/api/chat.postMessage', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json; charset=utf-8',
        Authorization: `Bearer ${this.token}`,
      },
      body: JSON.stringify(body),
    })
    const data = (await res.json()) as Record<string, unknown>
    return (data.ts as string) ?? ''
  }

  async sendTyping(channelId: string, _threadId?: string): Promise<void> {
    await fetch('https://slack.com/api/chat.postMessage', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${this.token}`,
      },
      body: JSON.stringify({ channel: channelId, text: '' }),
    })
  }

  on(handler: ChannelEventHandler): void {
    this.handlers.push(handler)
  }

  isRunning(): boolean {
    return this.running
  }

  handleEvent(body: Record<string, unknown>): void {
    const event = body.event as Record<string, unknown> | undefined
    if (!event) return
    if (event.type !== 'message' || event.subtype || event.bot_id) return

    const message: ChannelMessage = {
      id: String(event.ts ?? randomUUID()),
      channelId: String(event.channel ?? ''),
      userId: String(event.user ?? ''),
      userName: (body.authorizations as Array<Record<string, unknown>>)?.[0]?.user_id as string ?? event.user as string ?? 'unknown',
      text: String(event.text ?? ''),
      threadId: event.thread_ts as string ?? undefined,
      timestamp: new Date(Number(event.ts) * 1000).toISOString(),
    }

    for (const handler of this.handlers) {
      handler({ type: 'message', message })
    }
  }
}
