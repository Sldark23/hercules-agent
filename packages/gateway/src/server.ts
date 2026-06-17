import { createServer, type IncomingMessage, type ServerResponse } from 'node:http'
import { randomUUID, createHash } from 'node:crypto'
import type { Socket } from 'node:net'

export interface GatewayConfig {
  host: string
  port: number
  authToken?: string
  corsOrigins?: string[]
  maxPayloadSize?: number
  rateLimitWindow?: number
  rateLimitMaxRequests?: number
}

interface RateLimitEntry {
  count: number
  resetTime: number
}

export interface GatewayRoute {
  method: 'GET' | 'POST' | 'PUT' | 'DELETE' | 'PATCH'
  path: string
  handler: (req: IncomingMessage, res: ServerResponse, body?: unknown) => void | Promise<void>
}

export class GatewayServer {
  private server: ReturnType<typeof createServer>
  private routes: GatewayRoute[] = []
  private wsClients: Map<string, WebSocketClient> = new Map()
  private config: GatewayConfig
  private rateLimitMap: Map<string, RateLimitEntry> = new Map()
  private startTime = Date.now()

  constructor(config: Partial<GatewayConfig> = {}) {
    this.config = {
      host: config.host ?? '0.0.0.0',
      port: config.port ?? 18789,
      authToken: config.authToken ?? randomUUID(),
      corsOrigins: config.corsOrigins ?? ['*'],
      maxPayloadSize: config.maxPayloadSize ?? 10 * 1024 * 1024,
      rateLimitWindow: config.rateLimitWindow ?? 60000,
      rateLimitMaxRequests: config.rateLimitMaxRequests ?? 100,
    }
    this.server = createServer((req, res) => this.handleRequest(req, res))
  }

  route(r: GatewayRoute): void {
    this.routes.push(r)
  }

  routeAll(routes: GatewayRoute[]): void {
    this.routes.push(...routes)
  }

  addHealthCheckRoutes(): void {
    this.routes.push(
      {
        method: 'GET',
        path: '/health',
        handler: (_req, res) => {
          const uptime = Math.floor((Date.now() - this.startTime) / 1000)
          res.writeHead(200, { 'Content-Type': 'application/json' })
          res.end(JSON.stringify({
            status: 'ok',
            uptime_seconds: uptime,
            version: '0.2.3',
            timestamp: new Date().toISOString(),
          }))
        },
      },
      {
        method: 'GET',
        path: '/ready',
        handler: (_req, res) => {
          res.writeHead(200, { 'Content-Type': 'application/json' })
          res.end(JSON.stringify({
            ready: true,
            ws_clients: this.wsClients.size,
          }))
        },
      },
      {
        method: 'GET',
        path: '/v1/models',
        handler: (_req, res) => {
          res.writeHead(200, { 'Content-Type': 'application/json' })
          res.end(JSON.stringify({
            object: 'list',
            data: [
              { id: 'gpt-4o', object: 'model', created: Date.now(), owned_by: 'hercules' },
              { id: 'claude-sonnet-4-20250514', object: 'model', created: Date.now(), owned_by: 'hercules' },
              { id: 'llama3.2', object: 'model', created: Date.now(), owned_by: 'hercules' },
            ],
          }))
        },
      },
    )
  }

  addRateLimit(maxRequests?: number, windowMs?: number): void {
    this.config.rateLimitMaxRequests = maxRequests ?? this.config.rateLimitMaxRequests
    this.config.rateLimitWindow = windowMs ?? this.config.rateLimitWindow
  }

  private checkRateLimit(key: string): boolean {
    const now = Date.now()
    const entry = this.rateLimitMap.get(key)

    if (!entry || now > entry.resetTime) {
      this.rateLimitMap.set(key, {
        count: 1,
        resetTime: now + (this.config.rateLimitWindow ?? 60000),
      })
      return true
    }

    if (entry.count >= (this.config.rateLimitMaxRequests ?? 100)) {
      return false
    }

    entry.count++
    return true
  }

  addWsClient(id: string, client: WebSocketClient): void {
    this.wsClients.set(id, client)
  }

  removeWsClient(id: string): void {
    this.wsClients.delete(id)
  }

  getWsClient(id: string): WebSocketClient | undefined {
    return this.wsClients.get(id)
  }

  broadcast(type: string, payload: unknown): void {
    const msg = JSON.stringify({ type, payload, timestamp: new Date().toISOString() })
    for (const client of this.wsClients.values()) {
      if (client.ready) client.send(msg)
    }
  }

  async start(): Promise<void> {
    return new Promise((resolve) => {
      this.server.listen(this.config.port, this.config.host, () => {
        console.log(`[gateway] Listening on ${this.config.host}:${this.config.port}`)
        resolve()
      })
    })
  }

  async stop(): Promise<void> {
    for (const client of this.wsClients.values()) client.close()
    this.wsClients.clear()

    return new Promise((resolve) => {
      this.server.close(() => resolve())
    })
  }

  getUrl(): string {
    return `http://${this.config.host}:${this.config.port}`
  }

  getConfig(): Readonly<GatewayConfig> {
    return this.config
  }

  private async handleRequest(req: IncomingMessage, res: ServerResponse): Promise<void> {
    this.setCorsHeaders(res)

    if (req.method === 'OPTIONS') {
      res.writeHead(204).end()
      return
    }

    const url = new URL(req.url ?? '/', `http://${req.headers.host ?? 'localhost'}`)
    const path = url.pathname

    if (!this.authenticate(req) && path !== '/health' && path !== '/ready' && path !== '/v1/models') {
      res.writeHead(401, { 'Content-Type': 'application/json' })
      res.end(JSON.stringify({ error: 'Unauthorized' }))
      return
    }

    const clientIp = Array.isArray(req.headers['x-forwarded-for']) 
      ? req.headers['x-forwarded-for'][0] 
      : req.headers['x-forwarded-for'] 
      ?? req.socket?.remoteAddress 
      ?? 'unknown'

    if (!this.checkRateLimit(clientIp as string)) {
      res.writeHead(429, { 'Content-Type': 'application/json' })
      res.end(JSON.stringify({ error: 'Rate limit exceeded' }))
      return
    }

    for (const route of this.routes) {
      if (route.method !== req.method) continue
      if (!this.matchPath(route.path, path)) continue

      let body: unknown = undefined
      if (req.method === 'POST' || req.method === 'PUT' || req.method === 'PATCH') {
        body = await this.parseBody(req)
      }

      try {
        await route.handler(req, res, body)
      } catch (err) {
        res.writeHead(500, { 'Content-Type': 'application/json' })
        res.end(JSON.stringify({ error: (err as Error).message }))
      }
      return
    }

    res.writeHead(404, { 'Content-Type': 'application/json' })
    res.end(JSON.stringify({ error: 'Not found' }))
  }

  private matchPath(pattern: string, path: string): boolean {
    const patternParts = pattern.split('/')
    const pathParts = path.split('/')
    if (patternParts.length !== pathParts.length) return false

    for (let i = 0; i < patternParts.length; i++) {
      if (patternParts[i]!.startsWith(':')) continue
      if (patternParts[i] !== pathParts[i]) return false
    }
    return true
  }

  private async parseBody(req: IncomingMessage): Promise<unknown> {
    const chunks: Buffer[] = []
    let size = 0

    return new Promise((resolve, reject) => {
      req.on('data', (chunk: Buffer) => {
        size += chunk.length
        if (size > (this.config.maxPayloadSize ?? 10_000_000)) {
          reject(new Error('Payload too large'))
          req.destroy()
          return
        }
        chunks.push(chunk)
      })
      req.on('end', () => {
        const raw = Buffer.concat(chunks).toString()
        try { resolve(JSON.parse(raw)) }
        catch { resolve(raw) }
      })
      req.on('error', reject)
    })
  }

  private authenticate(req: IncomingMessage): boolean {
    const token = this.config.authToken
    if (!token) return true

    const auth = req.headers['authorization']
    if (!auth) return false

    if (auth.startsWith('Bearer ')) {
      return auth.slice(7) === token
    }
    return auth === token
  }

  private setCorsHeaders(res: ServerResponse): void {
    const origins = this.config.corsOrigins
    if (origins?.includes('*')) {
      res.setHeader('Access-Control-Allow-Origin', '*')
    } else if (origins?.length) {
      res.setHeader('Access-Control-Allow-Origin', origins[0]!)
    }
    res.setHeader('Access-Control-Allow-Methods', 'GET, POST, PUT, DELETE, PATCH, OPTIONS')
    res.setHeader('Access-Control-Allow-Headers', 'Content-Type, Authorization')
  }
}

export interface WebSocketClient {
  id: string
  ready: boolean
  send(data: string): void
  close(): void
  onMessage(handler: (data: string) => void): void
  onClose(handler: () => void): void
}

const WS_MAGIC_GUID = '258EAFA5-E914-47DA-95CA-5AB9A1F246B4'

function encodeWsFrame(data: string): Buffer {
  const payload = Buffer.from(data, 'utf-8')
  const len = payload.length
  let header: Buffer
  if (len < 126) {
    header = Buffer.alloc(2)
    header[0] = 0x81
    header[1] = len
  } else if (len < 65536) {
    header = Buffer.alloc(4)
    header[0] = 0x81
    header[1] = 126
    header.writeUInt16BE(len, 2)
  } else {
    header = Buffer.alloc(10)
    header[0] = 0x81
    header[1] = 127
    header.writeBigUInt64BE(BigInt(len), 2)
  }
  return Buffer.concat([header, payload])
}

function decodeWsFrame(buffer: Buffer): string | null {
  if (buffer.length < 2) return null
  const opcode = buffer[0]! & 0x0f
  if (opcode === 0x08) return null
  if (opcode !== 0x01) return null
  let offset = 2
  let len = buffer[1]! & 0x7f
  if (len === 126) {
    if (buffer.length < 4) return null
    len = buffer.readUInt16BE(2)
    offset = 4
  } else if (len === 127) {
    if (buffer.length < 10) return null
    len = Number(buffer.readBigUInt64BE(2))
    offset = 10
  }
  if (buffer.length < offset + len) return null
  const masked = (buffer[1]! & 0x80) !== 0
  if (masked) {
    const mask = buffer.subarray(offset, offset + 4)
    offset += 4
    const unmasked = Buffer.alloc(len)
    for (let i = 0; i < len; i++) {
      unmasked[i] = buffer[offset + i]! ^ mask[i % 4]!
    }
    return unmasked.toString('utf-8')
  }
  return buffer.subarray(offset, offset + len).toString('utf-8')
}

export class SimpleWebSocketServer {
  private server: ReturnType<typeof createServer>
  private clients: Map<string, SimpleWsClient> = new Map()
  private gateway: GatewayServer
  private port: number

  constructor(gateway: GatewayServer, port?: number) {
    this.gateway = gateway
    this.port = port ?? 18790
    this.server = createServer()

    this.server.on('upgrade', (req: IncomingMessage, socket: Socket, head: Buffer) => {
      const key = req.headers['sec-websocket-key']
      if (!key) {
        socket.destroy()
        return
      }

      const accept = createHash('sha1')
        .update(key + WS_MAGIC_GUID)
        .digest('base64')

      socket.write(
        'HTTP/1.1 101 Switching Protocols\r\n' +
        'Upgrade: websocket\r\n' +
        'Connection: Upgrade\r\n' +
        `Sec-WebSocket-Accept: ${accept}\r\n` +
        '\r\n'
      )

      const id = randomUUID()
      const client = new SimpleWsClient(id, socket)
      this.clients.set(id, client)
      this.gateway.addWsClient(id, client)

      socket.on('data', (data: Buffer) => {
        const msg = decodeWsFrame(data)
        if (msg === null) {
          client.close()
          return
        }
        client['onMsg']?.(msg)
      })

      socket.on('close', () => {
        client.close()
        this.clients.delete(id)
        this.gateway.removeWsClient(id)
      })

      socket.on('error', () => {
        client.close()
        this.clients.delete(id)
        this.gateway.removeWsClient(id)
      })

      if (head.length > 0) {
        const msg = decodeWsFrame(head)
        if (msg) client['onMsg']?.(msg)
      }
    })
  }

  getClientCount(): number {
    return this.clients.size
  }

  start(): void {
    this.server.listen(this.port, () => {
      console.log(`[gateway:ws] WebSocket server on :${this.port}`)
    })
  }

  stop(): void {
    for (const c of this.clients.values()) c.close()
    this.clients.clear()
    this.server.close()
  }

  broadcast(type: string, payload: unknown): void {
    const msg = JSON.stringify({ type, payload, timestamp: new Date().toISOString() })
    for (const c of this.clients.values()) c.send(msg)
  }
}

class SimpleWsClient {
  id: string
  ready = true
  private socket: Socket
  onMsg?: (data: string) => void
  private closeHandler?: () => void

  constructor(id: string, socket: Socket) {
    this.id = id
    this.socket = socket
  }

  send(data: string): void {
    if (!this.ready) return
    try {
      this.socket.write(encodeWsFrame(data))
    } catch {
      this.close()
    }
  }

  close(): void {
    if (!this.ready) return
    this.ready = false
    try {
      const buf = Buffer.alloc(2)
      buf[0] = 0x88
      buf[1] = 0x00
      this.socket.write(buf)
    } catch {}
    this.socket.end()
    this.closeHandler?.()
  }

  onMessage(handler: (data: string) => void): void { this.onMsg = handler }

  onClose(handler: () => void): void { this.closeHandler = handler }
}
