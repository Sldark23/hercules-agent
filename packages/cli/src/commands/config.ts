import { Command } from 'commander'
import { readFile, writeFile, access } from 'node:fs/promises'
import { homedir } from 'node:os'
import { join } from 'node:path'

const CONFIG_PATH = join(homedir(), '.hercules', 'config.json')

interface HerculesConfig {
  apiKey?: string
  defaultModel?: string
  provider?: string
  workspaceDir?: string
  theme?: 'dark' | 'light'
}

export const configCommand = new Command('config')
  .description('Manage Hercules configuration')
  .option('-s, --show', 'Show current config')
  .option('--set <key=value>', 'Set a config value (e.g. --set apiKey=sk-xxx)')
  .option('--get <key>', 'Get a specific config value')
  .option('--reset', 'Reset config to defaults')
  .action(async (options) => {
    if (options.reset) {
      const dir = join(homedir(), '.hercules')
      try {
        await access(dir)
        await writeFile(CONFIG_PATH, JSON.stringify({}, null, 2))
        console.log('[hercules] Config reset to defaults')
      } catch {
        console.log('[hercules] No config to reset')
      }
      return
    }

    let config: HerculesConfig = {}
    try {
      const raw = await readFile(CONFIG_PATH, 'utf-8')
      config = JSON.parse(raw)
    } catch {
      config = {}
    }

    if (options.set) {
      const eqIdx = options.set.indexOf('=')
      if (eqIdx === -1) {
        console.error('[hercules] Invalid format. Use --set key=value')
        return
      }
      const key = options.set.slice(0, eqIdx) as keyof HerculesConfig
      const value = options.set.slice(eqIdx + 1)
      config[key] = value as never
      const dir = join(homedir(), '.hercules')
      await access(dir).catch(() => require('node:fs').mkdirSync(dir, { recursive: true }))
      await writeFile(CONFIG_PATH, JSON.stringify(config, null, 2))
      console.log(`[hercules] Set ${key} = ${value}`)
      return
    }

    if (options.get) {
      const key = options.get as keyof HerculesConfig
      if (key in config) {
        console.log(config[key])
      } else {
        console.log(`[hercules] ${key} is not set`)
      }
      return
    }

    if (options.show || Object.keys(options).length === 0) {
      if (Object.keys(config).length === 0) {
        console.log('[hercules] No configuration found')
      } else {
        console.log('[hercules] Current configuration:')
        for (const [k, v] of Object.entries(config)) {
          const display = k.includes('key') || k.includes('token') ? '***' : v
          console.log(`  ${k}: ${display}`)
        }
      }
    }
  })
