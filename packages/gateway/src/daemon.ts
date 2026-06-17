/**
 * Gateway daemon — runs the GatewayServer persistently.
 * Designed to be invoked by systemd, launchd, or Windows Service Manager.
 */
import { GatewayServer } from './server.js'
import type { GatewayConfig } from './server.js'
import { readFile, writeFile } from 'node:fs/promises'
import { join, dirname } from 'node:path'
import { homedir } from 'node:os'
import { fileURLToPath } from 'node:url'

const __dirname = dirname(fileURLToPath(import.meta.url))
const PID_PATH = join(homedir(), '.hercules', 'gateway.pid')
const LOG_DIR = join(homedir(), '.hercules', 'logs')

async function loadConfig(): Promise<Partial<GatewayConfig>> {
  try {
    const configPath = join(homedir(), '.hercules', 'gateway.json')
    const raw = await readFile(configPath, 'utf-8')
    return JSON.parse(raw)
  } catch {
    return {}
  }
}

async function writePid(): Promise<void> {
  await writeFile(PID_PATH, String(process.pid))
}

async function main(): Promise<void> {
  await writePid()

  const config: Partial<GatewayConfig> = await loadConfig()
  const server = new GatewayServer({
    host: config.host ?? '0.0.0.0',
    port: config.port ?? 3000,
    authToken: config.authToken,
    corsOrigins: config.corsOrigins ?? ['*'],
    rateLimitMaxRequests: config.rateLimitMaxRequests ?? 100,
    rateLimitWindow: config.rateLimitWindow ?? 60000,
    ...config,
  })

  server.addHealthCheckRoutes()

  const { createOpenAICompatRoutes } = await import('./openai-http.js')
  server.routeAll(createOpenAICompatRoutes({
    chatComplete: async () => ({ id: '', content: '', usage: { input: 0, output: 0, total: 0 }, finish_reason: 'stop', model: '' } as any),
    chatCompleteStream: async function* () {},
  }))

  const shutdown = async () => {
    console.log('[gateway:daemon] Shutting down...')
    await server.stop()
    process.exit(0)
  }

  process.on('SIGINT', shutdown)
  process.on('SIGTERM', shutdown)
  process.on('uncaughtException', (err) => {
    console.error('[gateway:daemon] Uncaught exception:', err)
    process.exit(1)
  })

  await server.start()
  console.log(`[gateway:daemon] Listening on ${config.host ?? '0.0.0.0'}:${config.port ?? 3000} (pid ${process.pid})`)

  // Keep alive — GatewayServer manages its own listener
  await new Promise(() => {})
}

main().catch((err) => {
  console.error('[gateway:daemon] Fatal:', err)
  process.exit(1)
})
