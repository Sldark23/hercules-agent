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
    this.ws.onmessage = (event) => this.handleWS(typeof event.data === 'string' ? event.data : String(event.data))
    this.ws.onclose = () => {
      if (this.running) setTimeout(() => this.connect(), 5000)
    }
    this.ws.onerror = () => {}
  }

  private handleWS(raw: string): void {
    try {
      const pkt = JSON.parse(raw) as Record<string, unknown>
      const op = Number(pkt.op)
      const data = pkt.d

      if (typeof pkt.s === 'number') this.seq = pkt.s

      if (op === 10) {
        const d = data as Record<string, unknown> | undefined
        const heartbeat = Number((d?.heartbeat_interval ?? 0))
        this.ws?.send(JSON.stringify({
          op: 2,
          d: { token: this.token, intents: 1 << 15 | 1 << 9 | 1 << 12, properties: { os: 'linux', browser: 'hercules', device: 'hercules' } },
        }))
        this.heartbeatInterval = setInterval(() => {
          this.ws?.send(JSON.stringify({ op: 1, d: this.seq }))
        }, heartbeat)
      }

      if (op === 0 && pkt.t === 'READY' && data) {
        const d = data as Record<string, unknown>
        this.sessionId = typeof d.session_id === 'string' ? d.session_id : null
      }

      if (op === 0 && pkt.t === 'MESSAGE_CREATE') {
        const msg = data as Record<string, unknown> | undefined
        if (!msg) return
        const author = msg.author as Record<string, unknown> | undefined
        if (author?.bot) return

        const message: ChannelMessage = {
          id: String(msg.id ?? randomUUID()),
          channelId: String(msg.channel_id ?? ''),
          userId: String(author?.id ?? ''),
          userName: typeof author?.global_name === 'string' ? author.global_name : (typeof author?.username === 'string' ? author.username : 'unknown'),
          text: String(msg.content ?? ''),
          threadId: typeof (msg.thread as Record<string, unknown> | undefined)?.id === 'string' ? (msg.thread as Record<string, unknown>).id as string : undefined,
          timestamp: new Date(String(msg.timestamp ?? '')).toISOString(),
        }

        for (const handler of this.handlers) {
          handler({ type: 'message', message })
        }
      }
    } catch {}
  }
}
