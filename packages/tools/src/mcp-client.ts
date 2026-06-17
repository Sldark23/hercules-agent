import { z } from 'zod'
import { spawn, type ChildProcess } from 'node:child_process'
import { EventEmitter } from 'node:events'
import { request as httpRequest } from 'node:http'
import { request as httpsRequest } from 'node:https'
import type { RegisteredTool } from './registry.js'

export const McpCallInput = z.object({
  server: z.string().min(1),
  tool: z.string().min(1),
  arguments: z.record(z.unknown()).optional(),
  transport: z.enum(['stdio', 'http', 'sse']).optional().default('stdio'),
  command: z.string().optional(),
  args: z.array(z.string()).optional(),
  url: z.string().optional(),
  timeout: z.number().positive().max(120_000).optional().default(30_000),
})

export type McpCallInput = z.infer<typeof McpCallInput>

export type McpTransportType = 'stdio' | 'http' | 'sse'

interface McpToolDefinition {
  name: string
  description: string
  inputSchema: Record<string, unknown>
}

interface McpServerSession {
  id: string
  transport: McpTransportType
  process?: ChildProcess
  tools: McpToolDefinition[]
  emitter: EventEmitter
}

export class McpClient {
  private sessions: Map<string, McpServerSession> = new Map()

  async connect(config: McpServerConfig): Promise<string> {
    const id = `mcp-${config.name}-${Date.now()}`
    const emitter = new EventEmitter()

    let tools: McpToolDefinition[] = []

    if (config.transport === 'stdio') {
      tools = await this.connectStdio(id, config, emitter)
    } else if (config.transport === 'http') {
      tools = await this.connectHttp(id, config, emitter)
    }

    const session: McpServerSession = { id, transport: config.transport, tools, emitter }
    this.sessions.set(id, session)
    return id
  }

  async call(sessionId: string, tool: string, args: Record<string, unknown>): Promise<unknown> {
    const session = this.sessions.get(sessionId)
    if (!session) throw new Error(`MCP session "${sessionId}" not found`)

    switch (session.transport) {
      case 'stdio':
        return this.callStdio(session, tool, args)
      case 'http':
        return this.callHttp(session, tool, args)
      default:
        throw new Error(`Unsupported transport: ${session.transport}`)
    }
  }

  getTools(sessionId: string): McpToolDefinition[] {
    return this.sessions.get(sessionId)?.tools ?? []
  }

  async disconnect(sessionId: string): Promise<void> {
    const session = this.sessions.get(sessionId)
    if (!session) return
    if (session.process && !session.process.killed) {
      session.process.kill()
    }
    this.sessions.delete(sessionId)
  }

  disconnectAll(): void {
    for (const id of this.sessions.keys()) {
      this.disconnect(id)
    }
  }

  private async connectStdio(
    id: string,
    config: McpServerConfig,
    emitter: EventEmitter
  ): Promise<McpToolDefinition[]> {
    const cmd = config.command ?? 'npx'
    const args = config.args ?? ['-y', '@modelcontextprotocol/server-filesystem']

    const proc = spawn(cmd, args, {
      stdio: ['pipe', 'pipe', 'pipe'],
      env: { ...process.env, PATH: process.env.PATH },
    })

    const session = this.sessions.get(id)
    if (session) session.process = proc

    const initialize = {
      jsonrpc: '2.0' as const,
      id: 1,
      method: 'initialize',
      params: {
        protocolVersion: '2024-11-05',
        capabilities: { tools: {} },
        clientInfo: { name: 'hercules-agent', version: '0.1.0' },
      },
    }

    proc.stdin!.write(JSON.stringify(initialize) + '\n')

    return new Promise((resolve, reject) => {
      const timeout = setTimeout(() => reject(new Error('MCP stdio init timeout')), 15_000)
      let buf = ''

      proc.stdout!.on('data', (chunk: Buffer) => {
        buf += chunk.toString()
        const lines = buf.split('\n')
        buf = lines.pop() ?? ''

        for (const line of lines) {
          if (!line.trim()) continue
          try {
            const msg = JSON.parse(line)
            if (msg.id === 1 && msg.result) {
              clearTimeout(timeout)
              const capabilities = msg.result?.capabilities ?? {}
              const toolsResult = capabilities?.tools ?? {}

              const tools: McpToolDefinition[] = (toolsResult?.tools ?? []).map((t: Record<string, unknown>) => ({
                name: t.name as string,
                description: (t.description as string) ?? '',
                inputSchema: (t.inputSchema as Record<string, unknown>) ?? {},
              }))

              resolve(tools)
            }
          } catch {}
        }
      })

      proc.stderr!.on('data', (chunk: Buffer) => {
        emitter.emit('stderr', chunk.toString())
      })

      proc.on('error', (err) => { clearTimeout(timeout); reject(err) })
      proc.on('exit', (code) => {
        if (code !== 0) emitter.emit('exit', code)
      })
    })
  }

  private async connectHttp(
    id: string,
    config: McpServerConfig,
    _emitter: EventEmitter
  ): Promise<McpToolDefinition[]> {
    if (!config.url) throw new Error('url required for HTTP transport')
    const res = await this.httpFetch(config.url, {
      jsonrpc: '2.0',
      id: 1,
      method: 'initialize',
      params: { protocolVersion: '2024-11-05', capabilities: {}, clientInfo: { name: 'hercules', version: '0.1.0' } },
    })

    const capabilities = (res as Record<string, unknown>)?.result as Record<string, unknown> ?? {}
    const tools = ((capabilities?.tools as Record<string, unknown>)?.tools as Array<Record<string, unknown>>) ?? []
    return tools.map(t => ({
      name: t.name as string,
      description: (t.description as string) ?? '',
      inputSchema: (t.inputSchema as Record<string, unknown>) ?? {},
    }))
  }

  private async callStdio(session: McpServerSession, tool: string, args: Record<string, unknown>): Promise<unknown> {
    if (!session.process || !session.process.stdin) throw new Error('Session not connected')

    const request = {
      jsonrpc: '2.0',
      id: Date.now(),
      method: 'tools/call',
      params: { name: tool, arguments: args },
    }

    session.process.stdin.write(JSON.stringify(request) + '\n')

    return new Promise((resolve, reject) => {
      const timeout = setTimeout(() => reject(new Error('MCP call timeout')), 30_000)
      let buf = ''

      const handler = (chunk: Buffer) => {
        buf += chunk.toString()
        const lines = buf.split('\n')
        buf = lines.pop() ?? ''

        for (const line of lines) {
          if (!line.trim()) continue
          try {
            const msg = JSON.parse(line)
            if (msg.id === request.id) {
              clearTimeout(timeout)
              session.process!.stdout!.removeListener('data', handler)
              resolve((msg.result as Record<string, unknown>)?.content ?? msg.result)
            }
          } catch {}
        }
      }

      session.process?.stdout?.on('data', handler)
    })
  }

  private async callHttp(session: McpServerSession, tool: string, args: Record<string, unknown>): Promise<unknown> {
    const url = (this.sessions.get(session.id) as unknown as { url?: string })?.url
    if (!url) throw new Error('MCP HTTP URL not available')

    return this.httpFetch(url, {
      jsonrpc: '2.0',
      id: Date.now(),
      method: 'tools/call',
      params: { name: tool, arguments: args },
    })
  }

  private httpFetch(url: string, body: unknown): Promise<unknown> {
    const isHttps = url.startsWith('https')
    const caller = isHttps ? httpsRequest : httpRequest

    return new Promise((resolve, reject) => {
      const u = new URL(url)
      const data = JSON.stringify(body)
      const req = caller(u, {
        method: 'POST',
        hostname: u.hostname,
        port: u.port,
        path: u.pathname,
        headers: { 'Content-Type': 'application/json', 'Content-Length': Buffer.byteLength(data) },
        timeout: 30_000,
      }, (res) => {
        let buf = ''
        res.on('data', (chunk: Buffer) => { buf += chunk.toString() })
        res.on('end', () => {
          try { resolve(JSON.parse(buf)) }
          catch { resolve(buf) }
        })
      })
      req.on('error', reject)
      req.write(data)
      req.end()
    })
  }
}

export interface McpServerConfig {
  name: string
  transport: McpTransportType
  command?: string
  args?: string[]
  url?: string
}

const mcpClient = new McpClient()

export { mcpClient }

export function createMcpTool(): RegisteredTool {
  return {
    name: 'mcp_call',
    description: 'Call a tool on an MCP (Model Context Protocol) server. Connect to stdio, HTTP, or SSE servers.',
    inputSchema: McpCallInput,
    category: 'mcp',
    requiresApproval: false,
    handler: async (input, _ctx) => {
      const { server: _server, tool, arguments: args, transport, command, args: cmdArgs, url, timeout } = input as McpCallInput & { server: string }

      const sessionId = `mcp-auto-${transport}-${tool}`
      if (!mcpClient['sessions'].has(sessionId)) {
        await mcpClient.connect({ name: sessionId, transport, command, args: cmdArgs, url })
      }

      const result = await mcpClient.call(sessionId, tool, args ?? {})
      return { toolCallId: '', output: JSON.stringify(result, null, 2), metadata: { timeout } }
    },
  }
}
