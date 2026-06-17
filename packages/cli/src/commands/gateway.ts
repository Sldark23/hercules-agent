import { Command } from 'commander'
import { GatewayServer } from '@hercules/gateway'
import { readFile, writeFile } from 'node:fs/promises'
import { existsSync } from 'node:fs'
import { join, dirname } from 'node:path'
import { homedir } from 'node:os'
import { fileURLToPath } from 'node:url'
import { spawn, execSync } from 'node:child_process'

const __dirname = dirname(fileURLToPath(import.meta.url))
const HERCULES_DIR = join(homedir(), '.hercules')
const CONFIG_PATH = join(HERCULES_DIR, 'gateway.json')
const PID_PATH = join(HERCULES_DIR, 'gateway.pid')

const DEFAULT_CONFIG = {
  host: '0.0.0.0',
  port: 3000,
  authToken: crypto.randomUUID(),
  allowedOrigins: ['*'],
}

async function loadConfig(): Promise<Record<string, unknown>> {
  try {
    return JSON.parse(await readFile(CONFIG_PATH, 'utf-8'))
  } catch {
    return { ...DEFAULT_CONFIG }
  }
}

async function saveConfig(config: Record<string, unknown>): Promise<void> {
  await writeFile(CONFIG_PATH, JSON.stringify(config, null, 2))
}

function findDaemonJs(): string {
  const candidates = [
    join(__dirname, '..', '..', '..', 'gateway', 'dist', 'daemon.js'),
    join(__dirname, '..', '..', '..', '..', 'packages', 'gateway', 'dist', 'daemon.js'),
    join(HERCULES_DIR, 'agent', 'packages', 'gateway', 'dist', 'daemon.js'),
  ]
  for (const c of candidates) {
    if (existsSync(c)) return c
  }
  // default
  return join(HERCULES_DIR, 'agent', 'packages', 'gateway', 'dist', 'daemon.js')
}

let currentServer: GatewayServer | null = null

export const gatewayCommand = new Command('gateway')
  .description('Manage the Hercules Gateway')
  .addCommand(
    new Command('start')
      .description('Start the gateway server')
      .option('-p, --port <n>', 'Port', '3000')
      .option('--host <addr>', 'Host address', '0.0.0.0')
      .option('--daemon', 'Run as background daemon')
      .option('--service', 'Install and start as system service')
      .action(async (options) => {
        if (options.service) {
          const os = process.platform
          const scriptDir = join(__dirname, '..', '..', '..', '..', 'scripts')
          if (os === 'linux') {
            execSync(`sudo bash "${scriptDir}/install-service.sh"`, { stdio: 'inherit' })
          } else if (os === 'darwin') {
            execSync(`bash "${scriptDir}/install-service.sh"`, { stdio: 'inherit' })
          } else {
            console.log('[hercules] On Windows, use NSSM to install as service:')
            console.log(`  nssm install HerculesGateway "node" "${findDaemonJs()}"`)
          }
          return
        }

        if (options.daemon) {
          const daemonJs = findDaemonJs()
          if (!existsSync(daemonJs)) {
            console.error('[hercules] Gateway daemon.js not found. Build first: pnpm build')
            process.exit(1)
          }
          const child = spawn('node', [daemonJs], {
            detached: true,
            stdio: 'ignore',
            env: { ...process.env, NODE_ENV: 'production' },
          })
          child.unref()
          await writeFile(PID_PATH, String(child.pid ?? ''))
          console.log(`[hercules] Gateway daemon started (pid ${child.pid})`)
          return
        }

        const config = await loadConfig()
        const host = options.host ?? config.host ?? DEFAULT_CONFIG.host
        const port = parseInt(options.port, 10) ?? config.port ?? DEFAULT_CONFIG.port

        const server = new GatewayServer({
          host,
          port,
          authToken: config.authToken as string,
          corsOrigins: config.allowedOrigins as string[] ?? ['*'],
        })

        currentServer = server
        await server.start()
        console.log(`[hercules] Gateway listening on ${host}:${port}`)

        const shutdown = async () => {
          console.log('\n[hercules] Shutting down...')
          await server.stop()
          process.exit(0)
        }
        process.on('SIGINT', shutdown)
        process.on('SIGTERM', shutdown)
      })
  )
  .addCommand(
    new Command('stop')
      .description('Stop the gateway daemon')
      .action(async () => {
        if (currentServer) {
          await currentServer.stop()
          currentServer = null
          console.log('[hercules] Gateway stopped.')
          return
        }
        try {
          const pid = parseInt(await readFile(PID_PATH, 'utf-8'), 10)
          try { process.kill(pid, 'SIGTERM') } catch { /* ignore */ }
          console.log(`[hercules] Gateway daemon (pid ${pid}) stopped.`)
        } catch {
          console.log('[hercules] No running gateway found.')
        }
      })
  )
  .addCommand(
    new Command('status')
      .description('Show gateway status')
      .action(async () => {
        const config = await loadConfig()
        console.log(`Gateway config: ${JSON.stringify(config, null, 2)}`)
        try {
          const pid = parseInt(await readFile(PID_PATH, 'utf-8'), 10)
          try {
            process.kill(pid, 0)
            console.log(`Status: running (pid ${pid})`)
          } catch {
            console.log('Status: not running (stale PID file)')
          }
        } catch {
          console.log('Status: not running')
        }
      })
  )
  .addCommand(
    new Command('config')
      .description('Set gateway configuration')
      .argument('<key=value>', 'Config key=value (e.g. port=8080)')
      .action(async (kv) => {
        const eqIdx = kv.indexOf('=')
        if (eqIdx === -1) { console.error('Use key=value format'); return }
        const key = kv.slice(0, eqIdx)
        const value = kv.slice(eqIdx + 1)
        const config = await loadConfig()
        ;(config as Record<string, unknown>)[key] = isNaN(Number(value)) ? value : Number(value)
        await saveConfig(config)
        console.log(`[hercules] Gateway config set: ${key}=${config[key]}`)
      })
  )
