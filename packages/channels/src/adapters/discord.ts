import { randomUUID } from 'node:crypto'
import type { ChannelAdapter, ChannelMessage, ChannelEventHandler, OutboundMessage } from '../types.js'

export class DiscordAdapter implements ChannelAdapter {
  readonly name: string
  readonly type = 'discord'
  private token: string
  private handlers: ChannelEventHandler[] = []
  private running = false
  private ws: WebSocket | null = null
  private heartbeatInterval: ReturnType<typeof setInterval> | null = null
  private seq: number | null = null
  private sessionId: string | null = null

  constructor(name: string, token: string) {
    this.name = name
    this.token = token
  }

  async start(): Promise<void> {
    if (this.running) return
    this.running = true
    await this.connect()
    console.log(`[discord:${this.name}] Connected`)
  }

  async stop(): Promise<void> {
    this.running = false
    if (this.heartbeatInterval) clearInterval(this.heartbeatInterval)
    this.ws?.close()
    console.log(`[discord:${this.name}] Disconnected`)
  }

  async send(msg: OutboundMessage): Promise<string> {
    const body: Record<string, unknown> = { content: msg.text }
    if (msg.threadId) body.thread_id = msg.threadId

    const res = await fetch(`https://discord.com/api/v10/channels/${msg.channelId}/messages`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bot ${this.token}`,
      },
      body: JSON.stringify(body),
    })
    const data = (await res.json()) as Record<string, unknown>
    return String(data.id ?? '')
  }

  async sendTyping(channelId: string, _threadId?: string): Promise<void> {
    await fetch(`https://discord.com/api/v10/channels/${channelId}/typing`, {
      method: 'POST',
      headers: { Authorization: `Bot ${this.token}` },
    })
  }

  on(handler: ChannelEventHandler): void {
    this.handlers.push(handler)
  }

  isRunning(): boolean {
    return this.running
  }

  private async connect(): Promise<void> {
    const res = await fetch('https://discord.com/api/v10/gateway')
    const data = (await res.json()) as { url: string }
    const wsUrl = `${data.url}?v=10&encoding=json`

    this.ws = new WebSocket(wsUrl)
    this.ws.onmessage = (event) => this.handleWS(event.data as string)
    this.ws.onclose = () => {
      if (this.running) setTimeout(() => this.connect(), 5000)
    }
    this.ws.onerror = () => {}
  }

  private handleWS(raw: string): void {
    try {
      const pkt = JSON.parse(raw) as Record<string, unknown>
      const op = pkt.op as number
      const data = pkt.d as Record<string, unknown> | undefined

      if (pkt.s) this.seq = pkt.s as number

      if (op === 10) {
        const heartbeat = (data as Record<string, unknown>).heartbeat_interval as number
        this.ws?.send(JSON.stringify({
          op: 2,
          d: { token: this.token, intents: 1 << 15 | 1 << 9 | 1 << 12, properties: { os: 'linux', browser: 'hercules', device: 'hercules' } },
        }))
        this.heartbeatInterval = setInterval(() => {
          this.ws?.send(JSON.stringify({ op: 1, d: this.seq }))
        }, heartbeat)
      }

      if (op === 0 && (pkt.t as string) === 'READY') {
        this.sessionId = (data as Record<string, unknown>).session_id as string
      }

      if (op === 0 && (pkt.t as string) === 'MESSAGE_CREATE') {
        const msg = data as Record<string, unknown> | undefined
        if (!msg || msg.author?.bot) return

        const message: ChannelMessage = {
          id: String(msg.id ?? randomUUID()),
          channelId: String(msg.channel_id ?? ''),
          userId: String((msg.author as Record<string, unknown>)?.id ?? ''),
          userName: (msg.author as Record<string, unknown>)?.global_name as string
            ?? (msg.author as Record<string, unknown>)?.username as string ?? 'unknown',
          text: String(msg.content ?? ''),
          threadId: msg.thread?.id as string ?? undefined,
          timestamp: new Date(msg.timestamp as string).toISOString(),
        }

        for (const handler of this.handlers) {
          handler({ type: 'message', message })
        }
      }
    } catch {}
  }
}
