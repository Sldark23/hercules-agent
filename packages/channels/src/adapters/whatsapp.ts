import { randomUUID } from 'node:crypto'
import type { ChannelAdapter, ChannelMessage, ChannelEventHandler, OutboundMessage } from '../types.js'

export class WhatsAppAdapter implements ChannelAdapter {
  readonly name: string
  readonly type = 'whatsapp'
  private phoneNumberId: string
  private token: string
  private handlers: ChannelEventHandler[] = []
  private running = false
  private apiVersion = 'v21.0'

  constructor(name: string, phoneNumberId: string, token: string) {
    this.name = name
    this.phoneNumberId = phoneNumberId
    this.token = token
  }

  async start(): Promise<void> {
    if (this.running) return
    this.running = true
    console.log(`[whatsapp:${this.name}] Ready (webhook-based)`)
  }

  async stop(): Promise<void> {
    this.running = false
    console.log(`[whatsapp:${this.name}] Stopped`)
  }

  async send(msg: OutboundMessage): Promise<string> {
    const body: Record<string, unknown> = {
      messaging_product: 'whatsapp',
      to: msg.channelId,
      type: 'text',
      text: { body: msg.text },
    }

    const res = await fetch(
      `https://graph.facebook.com/${this.apiVersion}/${this.phoneNumberId}/messages`,
      {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${this.token}`,
        },
        body: JSON.stringify(body),
      }
    )
    const data = (await res.json()) as Record<string, unknown>
    const msgId = ((data.messages as Array<Record<string, unknown>>)?.[0])?.id as string ?? ''
    return msgId
  }

  async sendTyping(channelId: string, _threadId?: string): Promise<void> {
    await fetch(
      `https://graph.facebook.com/${this.apiVersion}/${this.phoneNumberId}/messages`,
      {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${this.token}`,
        },
        body: JSON.stringify({
          messaging_product: 'whatsapp',
          to: channelId,
          type: 'action',
          action: 'typing_on',
        }),
      }
    )
  }

  on(handler: ChannelEventHandler): void {
    this.handlers.push(handler)
  }

  isRunning(): boolean {
    return this.running
  }

  handleIncomingWebhook(body: Record<string, unknown>): void {
    const entries = body.entry as Array<Record<string, unknown>> ?? []
    for (const entry of entries) {
      const changes = entry.changes as Array<Record<string, unknown>> ?? []
      for (const change of changes) {
        const value = change.value as Record<string, unknown> ?? {}
        const messages = value.messages as Array<Record<string, unknown>> ?? []
        const contacts = value.contacts as Array<Record<string, unknown>> ?? []

        for (const msg of messages) {
          if (msg.type === 'text') {
            const contact = contacts[0] as Record<string, unknown> | undefined
            const profile = contact?.profile as Record<string, unknown> | undefined

            const valueMeta = value.metadata as Record<string, unknown> | undefined
            const message: ChannelMessage = {
              id: String(msg.id ?? randomUUID()),
              channelId: String(msg.from ?? valueMeta?.display_phone_number ?? ''),
              userId: String(msg.from ?? ''),
              userName: (profile?.name as string) ?? (contact?.wa_id as string) ?? 'unknown',
              text: (msg.text as Record<string, unknown>)?.body as string ?? '',
              timestamp: new Date(Number(msg.timestamp) * 1000).toISOString(),
            }

            for (const handler of this.handlers) {
              handler({ type: 'message', message })
            }
          }
        }
      }
    }
  }
}
