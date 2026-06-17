import { describe, it, expect, beforeEach } from 'vitest'
import { ChannelRegistry, TelegramAdapter, DiscordAdapter, WhatsAppAdapter, SlackAdapter } from './index.js'
import type { ChannelMessage } from './types.js'

// ─── ChannelRegistry ───────────────────────────────────────────────

describe('ChannelRegistry', () => {
  let registry: ChannelRegistry

  beforeEach(() => { registry = new ChannelRegistry() })

  it('registers adapters', () => {
    const adapter = new TelegramAdapter('test-bot', 'fake-token')
    registry.register(adapter)
    expect(registry.get('test-bot')).toBeDefined()
    expect(registry.count()).toBe(1)
  })

  it('lists adapters by type', () => {
    registry.register(new TelegramAdapter('tg', 'tok'))
    registry.register(new DiscordAdapter('dc', 'tok'))
    expect(registry.list('telegram')).toHaveLength(1)
    expect(registry.list('discord')).toHaveLength(1)
  })

  it('removes adapters', () => {
    registry.register(new TelegramAdapter('t', 'k'))
    registry.remove('t')
    expect(registry.count()).toBe(0)
  })

  it('forwards events to global handlers', () => {
    registry.register(new TelegramAdapter('t', 'k'))
    const events: string[] = []
    registry.on((e) => events.push(e.type))
    const adapter = registry.get('t') as TelegramAdapter
    adapter['handlers'].forEach(h => h({ type: 'message', message: { id: '1', channelId: 'c', userId: 'u', text: 'hi', timestamp: new Date().toISOString() } }))
    expect(events).toContain('message')
  })
})

// ─── Channel Adapters ──────────────────────────────────────────────

describe('TelegramAdapter', () => {
  it('creates with name and token', () => {
    const adapter = new TelegramAdapter('mybot', '123:abc')
    expect(adapter.name).toBe('mybot')
    expect(adapter.type).toBe('telegram')
    expect(adapter.isRunning()).toBe(false)
  })

  it('start and stop', async () => {
    const adapter = new TelegramAdapter('mybot', '123:abc')
    await adapter.start()
    expect(adapter.isRunning()).toBe(true)
    await adapter.stop()
    expect(adapter.isRunning()).toBe(false)
  })
})

describe('DiscordAdapter', () => {
  it('creates with name and token', () => {
    const adapter = new DiscordAdapter('mybot', 'discord-token')
    expect(adapter.name).toBe('mybot')
    expect(adapter.type).toBe('discord')
  })
})

describe('WhatsAppAdapter', () => {
  it('creates with name, phone, and token', () => {
    const adapter = new WhatsAppAdapter('wa', '123456789', 'token')
    expect(adapter.name).toBe('wa')
    expect(adapter.type).toBe('whatsapp')
  })

  it('handles incoming webhook', () => {
    const adapter = new WhatsAppAdapter('wa', '123456789', 'token')
    const messages: ChannelMessage[] = []
    adapter.on((e) => { if (e.type === 'message') messages.push(e.message) })

    adapter.handleIncomingWebhook({
      entry: [{
        changes: [{
          value: {
            metadata: { display_phone_number: '555-1234' },
            messages: [{ id: 'msg1', from: '555-5678', type: 'text', text: { body: 'Hello!' }, timestamp: '1000000000' }],
            contacts: [{ profile: { name: 'Alice' }, wa_id: '555-5678' }],
          },
        }],
      }],
    })

    expect(messages).toHaveLength(1)
    expect(messages[0]!.text).toBe('Hello!')
    expect(messages[0]!.userName).toBe('Alice')
  })
})

describe('SlackAdapter', () => {
  it('creates with name and token', () => {
    const adapter = new SlackAdapter('slack', 'xoxb-token')
    expect(adapter.name).toBe('slack')
    expect(adapter.type).toBe('slack')
  })

  it('handles incoming events', () => {
    const adapter = new SlackAdapter('slack', 'xoxb-token')
    const messages: ChannelMessage[] = []
    adapter.on((e) => { if (e.type === 'message') messages.push(e.message) })

    adapter.handleEvent({
      event: {
        type: 'message',
        channel: 'C123',
        user: 'U456',
        text: 'Test message',
        ts: '1000000000.000100',
      },
    })

    expect(messages).toHaveLength(1)
    expect(messages[0]!.text).toBe('Test message')
    expect(messages[0]!.channelId).toBe('C123')
  })

  it('ignores bot messages', () => {
    const adapter = new SlackAdapter('slack', 'xoxb-token')
    const messages: ChannelMessage[] = []
    adapter.on((e) => { if (e.type === 'message') messages.push(e.message) })

    adapter.handleEvent({
      event: { type: 'message', subtype: 'bot_message', bot_id: 'B999', channel: 'C1', user: 'U1', text: 'bot msg', ts: '1' },
    })

    expect(messages).toHaveLength(0)
  })
})
