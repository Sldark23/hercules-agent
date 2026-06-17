import { Command } from 'commander'
import { readFile } from 'node:fs/promises'
import { join } from 'node:path'

interface PackageJson {
  name: string
  version: string
  description?: string
}

export const statusCommand = new Command('status')
  .description('Show Hercules agent status and system info')
  .option('-v, --verbose', 'Show detailed info')
  .action(async (options) => {
    const pkgPath = join(import.meta.dirname, '..', '..', '..', '..', 'package.json')
    let rootPkg: PackageJson = { name: 'unknown', version: '0.0.0' }

    try {
      const raw = await readFile(join(import.meta.dirname, '..', '..', 'package.json'), 'utf-8')
      rootPkg = JSON.parse(raw)
    } catch {}

    const nodeVersion = process.version
    const platform = process.platform
    const arch = process.arch
    const memory = process.memoryUsage()

    console.log(`[hercules] Agent: ${rootPkg.name ?? 'hercules-agent'} v${rootPkg.version ?? '0.1.0'}`)
    console.log(`[hercules] Node.js: ${nodeVersion} (${platform} ${arch})`)
    console.log(`[hercules] Memory: ${(memory.rss / 1024 / 1024).toFixed(1)} MB RSS`)

    if (options.verbose) {
      console.log(`[hercules] Heap: ${(memory.heapUsed / 1024 / 1024).toFixed(1)}/${(memory.heapTotal / 1024 / 1024).toFixed(1)} MB`)
      console.log(`[hercules] CWD: ${process.cwd()}`)
      console.log(`[hercules] PID: ${process.pid}`)
      console.log(`[hercules] Uptime: ${(process.uptime() / 60).toFixed(1)} min`)
    }
  })
