import { Command } from 'commander'
import { readFile } from 'node:fs/promises'
import { join } from 'node:path'
import { execSync } from 'node:child_process'
import { logger } from '../logger.js'

interface PackageJson {
  name: string
  version: string
  description?: string
}

function getBehindCount(): number | null {
  try {
    const out = execSync('git rev-list --count HEAD..origin/main 2>/dev/null', { timeout: 5000, encoding: 'utf-8' }).trim()
    return Number(out)
  } catch {
    return null
  }
}

export const statusCommand = new Command('status')
  .description('Show Hercules agent status and system info')
  .option('-v, --verbose', 'Show detailed info')
  .action(async (options) => {
    let rootPkg: PackageJson = { name: 'unknown', version: '0.0.0' }
    try {
      const raw = await readFile(join(import.meta.dirname, '..', '..', 'package.json'), 'utf-8')
      rootPkg = JSON.parse(raw)
    } catch {}

    const nodeVersion = process.version
    const platform = process.platform
    const arch = process.arch
    const memory = process.memoryUsage()
    const behind = getBehindCount()

    logger.info(`Agent: ${rootPkg.name ?? 'hercules-agent'} v${rootPkg.version ?? '0.1.0'}`)
    logger.info(`Node.js: ${nodeVersion} (${platform} ${arch})`)
    logger.info(`Memory: ${(memory.rss / 1024 / 1024).toFixed(1)} MB RSS`)

    if (behind !== null) {
      if (behind === 0) {
        logger.info('Updates: up to date')
      } else {
        logger.warn(`Updates: ${behind} commit${behind !== 1 ? 's' : ''} behind (run 'hercules update')`)
      }
    }

    const { ToolRegistry, createExecTool, createFileTools, createBrowserTool } = await import('@hercules/tools')
    const reg = new ToolRegistry()
    reg.register(createExecTool())
    reg.registerBatch(createFileTools(process.cwd()))
    reg.register(createBrowserTool())
    logger.info(`Tools: ${reg.count()} registered (exec, file, browser)`)

    if (options.verbose) {
      logger.info(`Heap: ${(memory.heapUsed / 1024 / 1024).toFixed(1)}/${(memory.heapTotal / 1024 / 1024).toFixed(1)} MB`)
      logger.info(`CWD: ${process.cwd()}`)
      logger.info(`PID: ${process.pid}`)
      logger.info(`Uptime: ${(process.uptime() / 60).toFixed(1)} min`)
      logger.info(`Streaming: supported (use --stream flag)`)
      logger.info(`Log level: ${process.env.HERCULES_LOG_LEVEL ?? 'info'}`)
    }
  })
