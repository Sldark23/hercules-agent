import { Command } from 'commander'
import { readdir, readFile } from 'node:fs/promises'
import { join } from 'node:path'
import { existsSync } from 'node:fs'

export const inspectCommand = new Command('inspect')
  .description('Inspect internal Hercules state')
  .argument('[target]', 'Target to inspect: memory, sessions, config, plugins, skills, jobs')
  .option('--json', 'Output as JSON')
  .action(async (target, options) => {
    const targets = target ?? 'all'
    const targetsToShow = targets === 'all' ? ['memory', 'sessions', 'config', 'plugins', 'skills', 'jobs'] : [targets]

    const output: Record<string, unknown> = {}

    for (const t of targetsToShow) {
      switch (t) {
        case 'memory': {
          const mem = process.memoryUsage()
          output.memory = {
            rss: `${(mem.rss / 1024 / 1024).toFixed(1)} MB`,
            heapUsed: `${(mem.heapUsed / 1024 / 1024).toFixed(1)} MB`,
            heapTotal: `${(mem.heapTotal / 1024 / 1024).toFixed(1)} MB`,
            external: `${(mem.external / 1024 / 1024).toFixed(1)} MB`,
          }
          break
        }
        case 'sessions': {
          const sessionsDir = join(process.cwd(), 'data')
          if (existsSync(sessionsDir)) {
            const files = await readdir(sessionsDir)
            output.sessions = { dir: sessionsDir, files }
          } else {
            output.sessions = { dir: sessionsDir, exists: false }
          }
          break
        }
        case 'config': {
          const configPath = join(process.cwd(), 'hercules.json')
          if (existsSync(configPath)) {
            const raw = await readFile(configPath, 'utf-8')
            try { output.config = JSON.parse(raw) }
            catch { output.config = raw.slice(0, 500) }
          } else {
            output.config = { exists: false }
          }
          break
        }
        case 'plugins': {
          const pluginsDir = join(process.cwd(), 'plugins')
          if (existsSync(pluginsDir)) {
            const dirs = await readdir(pluginsDir)
            output.plugins = { dir: pluginsDir, count: dirs.length, names: dirs }
          } else {
            output.plugins = { dir: pluginsDir, exists: false }
          }
          break
        }
        case 'skills': {
          const skillsDir = join(process.cwd(), 'skills')
          if (existsSync(skillsDir)) {
            const dirs = await readdir(skillsDir)
            output.skills = { dir: skillsDir, count: dirs.length, names: dirs }
          } else {
            output.skills = { dir: skillsDir, exists: false }
          }
          break
        }
        case 'jobs': {
          const jobsPath = join(process.cwd(), 'data', 'scheduler.json')
          if (existsSync(jobsPath)) {
            const raw = await readFile(jobsPath, 'utf-8')
            try { output.jobs = JSON.parse(raw) }
            catch { output.jobs = 'unparseable' }
          } else {
            output.jobs = { exists: false }
          }
          break
        }
        default:
          output[t] = { error: `Unknown target "${t}"` }
      }
    }

    if (options.json) {
      console.log(JSON.stringify(output, null, 2))
    } else {
      for (const [key, value] of Object.entries(output)) {
        console.log(`[hercules:inspect] ${key}:`)
        if (typeof value === 'object' && value !== null) {
          for (const [k, v] of Object.entries(value as Record<string, unknown>)) {
            const display = typeof v === 'object' ? JSON.stringify(v) : String(v)
            console.log(`  ${k}: ${display}`)
          }
        } else {
          console.log(`  ${String(value)}`)
        }
      }
    }
  })
