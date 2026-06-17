import { randomUUID } from 'node:crypto'
import type { ChannelAdapter, ChannelMessage, ChannelEventHandler, OutboundMessage } from '../types.js'
import { withRetry } from '../retry.js'
import type { RetryConfig } from '../retry.js'

export type WebhookAuthType = 'bearer' | 'custom-header' | 'query-param' | 'none'

export interface WebhookAuthConfig {
  type: WebhookAuthType
  value?: string
  headerName?: string
  queryParam?: string
}

export interface WebhookAdapterConfig {
  name: string
  webhookUrl: string
  auth?: WebhookAuthConfig
  retry?: Partial<RetryConfig>
}

export class WebhookAdapter implements ChannelAdapter {
  readonly name: string
  readonly type = 'webhook'
  private config: WebhookAdapterConfig
  private handlers: ChannelEventHandler[] = []
  private running = false

  constructor(config: WebhookAdapterConfig) {
    this.name = config.name
    this.config = config
  }

  async start(): Promise<void> {
    if (this.running) return
    this.running = true
    console.log(`[webhook:${this.name}] Ready`)
  }

  async stop(): Promise<void> {
    this.running = false
    console.log(`[webhook:${this.name}] Stopped`)
  }

  async send(msg: OutboundMessage): Promise<string> {
    const headers: Record<string, string> = { 'Content-Type': 'application/json' }

    if (this.config.auth) {
      switch (this.config.auth.type) {
        case 'bearer':
          headers['Authorization'] = `Bearer ${this.config.auth.value}`
          break
        case 'custom-header':
          headers[this.config.auth.headerName ?? 'X-Webhook-Token'] = this.config.auth.value ?? ''
          break
      }
    }

    let url = this.config.webhookUrl
    if (this.config.auth?.type === 'query-param' && this.config.auth.queryParam) {
      url += `?${this.config.auth.queryParam}=${encodeURIComponent(this.config.auth.value ?? '')}`
    }

    const response = await withRetry(
      async () => {
        const res = await fetch(url, {
          method: 'POST',
          headers,
          body: JSON.stringify({
            channel: msg.channelId,
            text: msg.text,
            userId: msg.userId,
            threadId: msg.threadId,
            parseMode: msg.parseMode,
            attachments: msg.attachments,
          }),
        })
        if (!res.ok) {
          const err = new Error(`Webhook HTTP ${res.status}`) as Error & { status: number }
          err.status = res.status
          throw err
        }
        return res
      },
      this.config.retry,
      `webhook:${this.name}`
    )

    const data = await response.json().catch(() => ({}))
    return (data as Record<string, unknown>).id as string ?? randomUUID()
  }

  async sendTyping(_channelId: string, _threadId?: string): Promise<void> {
    // typing not supported for generic webhooks
  }

  on(handler: ChannelEventHandler): void {
    this.handlers.push(handler)
  }

  isRunning(): boolean {
    return this.running
  }

  handleIncoming(body: Record<string, unknown>): void {
    const message: ChannelMessage = {
      id: randomUUID(),
      channelId: (body.channelId as string) ?? (body.channel as string) ?? 'webhook',
      userId: (body.userId as string) ?? (body.from as string) ?? 'unknown',
      userName: (body.userName as string) ?? (body.user as string),
      text: (body.text as string) ?? (body.content as string) ?? '',
      timestamp: new Date().toISOString(),
    }

    for (const handler of this.handlers) {
      handler({ type: 'message', message })
    }
  }
}
