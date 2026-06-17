import { randomUUID } from 'node:crypto'
import type { ChannelAdapter, ChannelMessage, ChannelEventHandler, OutboundMessage } from '../types.js'

export class TelegramAdapter implements ChannelAdapter {
  readonly name: string
  readonly type = 'telegram'
  private token: string
  private handlers: ChannelEventHandler[] = []
  private running = false
  private pollInterval: ReturnType<typeof setInterval> | null = null
  private lastOffset = 0

  constructor(name: string, token: string) {
    this.name = name
    this.token = token
  }

  async start(): Promise<void> {
    if (this.running) return
    this.running = true
    this.poll()
    console.log(`[telegram:${this.name}] Started polling`)
  }

  async stop(): Promise<void> {
    this.running = false
    if (this.pollInterval) clearInterval(this.pollInterval)
    this.pollInterval = null
    console.log(`[telegram:${this.name}] Stopped`)
  }

  async send(msg: OutboundMessage): Promise<string> {
    const chatId = msg.channelId
    const body: Record<string, unknown> = {
      chat_id: chatId,
      text: msg.text,
      parse_mode: msg.parseMode === 'html' ? 'HTML' : msg.parseMode === 'markdown' ? 'MarkdownV2' : undefined,
    }
    if (msg.threadId) body.message_thread_id = msg.threadId
    if (msg.attachments?.length) {
      for (const att of msg.attachments) {
        body.photo = att.url
      }
    }

    const res = await fetch(`https://api.telegram.org/bot${this.token}/sendMessage`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    })
    const data = (await res.json()) as Record<string, unknown>
    return String((data.result as Record<string, unknown>)?.message_id ?? '')
  }

  async sendTyping(channelId: string, _threadId?: string): Promise<void> {
    await fetch(`https://api.telegram.org/bot${this.token}/sendChatAction`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ chat_id: channelId, action: 'typing' }),
    })
  }

  on(handler: ChannelEventHandler): void {
    this.handlers.push(handler)
  }

  isRunning(): boolean {
    return this.running
  }

  private async poll(): Promise<void> {
    const poll = async () => {
      if (!this.running) return
      try {
        const url = `https://api.telegram.org/bot${this.token}/getUpdates?offset=${this.lastOffset + 1}&timeout=30`
        const res = await fetch(url)
        const data = (await res.json()) as Record<string, unknown>

        if (!data.ok) return
        const updates = data.result as Array<Record<string, unknown>> ?? []
        for (const update of updates) {
          this.lastOffset = update.update_id as number
          this.handleUpdate(update)
        }
      } catch {}
    }
    this.pollInterval = setInterval(poll, 2000)
    poll()
  }

  private handleUpdate(update: Record<string, unknown>): void {
    const msg = update.message as Record<string, unknown> | undefined
    if (!msg) return

    const text = msg.text as string | undefined
    if (!text) return

    const chat = msg.chat as Record<string, unknown> | undefined
    const from = msg.from as Record<string, unknown> | undefined

    const message: ChannelMessage = {
      id: String(msg.message_id ?? randomUUID()),
      channelId: String(chat?.id ?? ''),
      userId: String(from?.id ?? ''),
      userName: from?.first_name as string ?? from?.username as string ?? 'unknown',
      text,
      threadId: msg.message_thread_id as string ?? undefined,
      timestamp: new Date((msg.date as number) * 1000).toISOString(),
    }

    for (const handler of this.handlers) {
      handler({ type: 'message', message })
    }
  }
}
