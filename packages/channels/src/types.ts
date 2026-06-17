import { z } from 'zod'

export const ChannelMessageSchema = z.object({
  id: z.string(),
  channelId: z.string(),
  userId: z.string(),
  userName: z.string().optional(),
  text: z.string(),
  threadId: z.string().optional(),
  attachments: z.array(z.object({
    type: z.enum(['image', 'audio', 'video', 'file']),
    url: z.string(),
    name: z.string().optional(),
    mimeType: z.string().optional(),
  })).optional(),
  metadata: z.record(z.unknown()).optional(),
  timestamp: z.string(),
})

export type ChannelMessage = z.infer<typeof ChannelMessageSchema>

export interface OutboundMessage {
  text: string
  channelId: string
  userId?: string
  threadId?: string
  attachments?: Array<{ type: string; url: string; name?: string }>
  parseMode?: 'markdown' | 'html' | 'none'
}

export interface ChannelAdapterConfig {
  enabled: boolean
  name: string
  type: string
  credentials?: Record<string, string>
  options?: Record<string, unknown>
}

export type ChannelEvent =
  | { type: 'message'; message: ChannelMessage }
  | { type: 'edited_message'; message: ChannelMessage }
  | { type: 'member_joined'; channelId: string; userId: string }
  | { type: 'member_left'; channelId: string; userId: string }
  | { type: 'reaction'; channelId: string; messageId: string; userId: string; emoji: string }
  | { type: 'error'; channelId: string; error: string }

export type ChannelEventHandler = (event: ChannelEvent) => void | Promise<void>

export interface ChannelAdapter {
  readonly name: string
  readonly type: string

  start(): Promise<void>
  stop(): Promise<void>
  send(message: OutboundMessage): Promise<string>
  sendTyping(channelId: string, threadId?: string): Promise<void>
  on(handler: ChannelEventHandler): void
  isRunning(): boolean
}
