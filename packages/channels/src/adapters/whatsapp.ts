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
    const msgs = data.messages
    const msgId = msgs && Array.isArray(msgs) && msgs.length > 0 ? String((msgs[0] as Record<string, unknown>)?.id ?? '') : ''
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
    const entries = body.entry
    if (!Array.isArray(entries)) return
    for (const entry of entries) {
      const changes = (entry as Record<string, unknown>).changes
      if (!Array.isArray(changes)) continue
      for (const change of changes) {
        const value = (change as Record<string, unknown>).value as Record<string, unknown> | undefined
        if (!value) continue
        const messages = value.messages
        const contacts = value.contacts
        if (!Array.isArray(messages)) continue

        for (const msg of messages) {
          const m = msg as Record<string, unknown>
          if (m.type === 'text') {
            const c = Array.isArray(contacts) && contacts.length > 0 ? contacts[0] as Record<string, unknown> : undefined
            const profile = c?.profile as Record<string, unknown> | undefined
            const valueMeta = value.metadata as Record<string, unknown> | undefined

            const textBody = m.text as Record<string, unknown> | undefined

            const message: ChannelMessage = {
              id: String(m.id ?? randomUUID()),
              channelId: String(m.from ?? valueMeta?.display_phone_number ?? ''),
              userId: String(m.from ?? ''),
              userName: typeof profile?.name === 'string' ? profile.name : (typeof c?.wa_id === 'string' ? c.wa_id : 'unknown'),
              text: typeof textBody?.body === 'string' ? textBody.body : '',
              timestamp: new Date(Number(m.timestamp) * 1000).toISOString(),
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
