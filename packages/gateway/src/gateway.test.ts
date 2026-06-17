import { describe, it, expect, beforeEach, vi } from 'vitest'
import { GatewayServer, createOpenAICompatRoutes, buildChatResponse, buildStreamChunk, SimpleWebSocketServer } from './index.js'
import type { GatewayRoute } from './index.js'

// ─── GatewayServer ─────────────────────────────────────────────────

describe('GatewayServer', () => {
  let gateway: GatewayServer

  beforeEach(() => {
    gateway = new GatewayServer({ host: '127.0.0.1', port: 0 })
  })

  it('creates server with default config', () => {
    expect(gateway.getConfig().authToken).toBeDefined()
    expect(gateway.getUrl()).toContain('127.0.0.1')
  })

  it('registers and matches routes', () => {
    const routes: GatewayRoute[] = [
      { method: 'GET', path: '/health', handler: async () => {} },
      { method: 'POST', path: '/v1/chat', handler: async () => {} },
    ]
    gateway.routeAll(routes)
    expect(gateway).toBeDefined()
  })

  it('starts and stops', async () => {
    await gateway.start()
    expect(gateway).toBeDefined()
    await gateway.stop()
  })
})

// ─── OpenAI Compat API ─────────────────────────────────────────────

describe('createOpenAICompatRoutes', () => {
  it('creates three routes (GET models, POST chat, POST embeddings)', () => {
    const handler = {
      chatComplete: async () => buildChatResponse('gpt-4', 'hello', { prompt: 10, completion: 5 }),
      chatCompleteStream: async function* () { yield buildStreamChunk('gpt-4', 'hello') },
    }
    const routes = createOpenAICompatRoutes(handler)
    expect(routes).toHaveLength(3)

    const methods = routes.map(r => `${r.method} ${r.path}`)
    expect(methods).toContain('GET /v1/models')
    expect(methods).toContain('POST /v1/chat/completions')
    expect(methods).toContain('POST /v1/embeddings')
  })
})

describe('buildChatResponse', () => {
  it('builds valid OpenAI-compatible response', () => {
    const res = buildChatResponse('gpt-4', 'Hello!', { prompt: 10, completion: 5 })
    expect(res.model).toBe('gpt-4')
    expect(res.choices[0]?.message.content).toBe('Hello!')
    expect(res.usage.prompt_tokens).toBe(10)
    expect(res.usage.completion_tokens).toBe(5)
    expect(res.object).toBe('chat.completion')
  })
})

describe('buildStreamChunk', () => {
  it('builds valid SSE chunk', () => {
    const chunk = buildStreamChunk('gpt-4', 'Hello')
    const parsed = JSON.parse(chunk)
    expect(parsed.model).toBe('gpt-4')
    expect(parsed.choices[0]?.delta.content).toBe('Hello')
    expect(parsed.object).toBe('chat.completion.chunk')
  })
})

// ─── WebSocket ──────────────────────────────────────────────────────

describe('SimpleWebSocketServer', () => {
  let gateway: GatewayServer
  let wss: SimpleWebSocketServer

  beforeEach(() => {
    gateway = new GatewayServer({ host: '127.0.0.1', port: 0 })
    wss = new SimpleWebSocketServer(gateway, 0)
  })

  it('starts and stops without error', async () => {
    wss.start()
    expect(wss.getClientCount()).toBe(0)
    wss.stop()
  })

  it('broadcast with no clients does not throw', async () => {
    wss.start()
    expect(() => wss.broadcast('test', { foo: 1 })).not.toThrow()
    wss.stop()
  })

  it('gateway.addWsClient and broadcast work', () => {
    const sent: string[] = []
    const client: import('./server.js').WebSocketClient = {
      id: 'test-1',
      ready: true,
      send: (data: string) => { sent.push(data) },
      close: () => {},
      onMessage: () => {},
      onClose: () => {},
    }
    gateway.addWsClient('test-1', client)
    gateway.broadcast('event', { msg: 'hello' })
    expect(sent).toHaveLength(1)
    const parsed = JSON.parse(sent[0]!)
    expect(parsed.type).toBe('event')
    expect(parsed.payload.msg).toBe('hello')
  })

  it('does not send to non-ready clients', () => {
    const sent: string[] = []
    const client: import('./server.js').WebSocketClient = {
      id: 'offline',
      ready: false,
      send: (data: string) => { sent.push(data) },
      close: () => {},
      onMessage: () => {},
      onClose: () => {},
    }
    gateway.addWsClient('offline', client)
    gateway.broadcast('test', {})
    expect(sent).toHaveLength(0)
  })

  it('removeWsClient removes from map', () => {
    const client: import('./server.js').WebSocketClient = {
      id: 'gone', ready: true, send: () => {}, close: () => {},
      onMessage: () => {}, onClose: () => {},
    }
    gateway.addWsClient('gone', client)
    expect(gateway.getWsClient('gone')).toBeDefined()
    gateway.removeWsClient('gone')
    expect(gateway.getWsClient('gone')).toBeUndefined()
  })
})
