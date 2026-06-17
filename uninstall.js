#!/usr/bin/env node
/**
 * Hercules Agent — Universal uninstaller
 * Removes all installed files, wrappers, and PATH entries.
 */
import { execSync } from 'node:child_process'
import { existsSync } from 'node:fs'
import { readFile, writeFile, rm } from 'node:fs/promises'
import { homedir, platform } from 'node:os'
import { join, dirname } from 'node:path'
import { fileURLToPath } from 'node:url'

const __dirname = dirname(fileURLToPath(import.meta.url))
const isWindows = platform() === 'win32'

const HERCULES_HOME = process.env.HERCULES_HOME || join(homedir(), '.hercules', 'agent')
const BIN_DIR = process.env.HERCULES_BIN || join(homedir(), '.hercules', 'bin')

const BOLD = '\x1b[1m'
const GREEN = '\x1b[32m'
const YELLOW = '\x1b[33m'
const RED = '\x1b[31m'
const NC = '\x1b[0m'

function log(msg, color = GREEN) { console.log(`${color}${msg}${NC}`) }

async function main() {
  const args = process.argv.slice(2)

  if (args.includes('--help') || args.includes('-h')) {
    console.log(`${BOLD}Hercules Agent Uninstaller${NC}

${BOLD}Usage:${NC}
  node uninstall.js              Run uninstaller
  node uninstall.js --force      Skip confirmation
  node uninstall.js --help       Show this help
`)
    return
  }

  const force = args.includes('--force')

  if (!existsSync(HERCULES_HOME) && !existsSync(BIN_DIR)) {
    log('No Hercules Agent installation found.', YELLOW)
    return
  }

  if (!force) {
    log(`${BOLD}This will remove Hercules Agent completely:${NC}`, RED)
    if (existsSync(HERCULES_HOME)) log(`  • ${HERCULES_HOME}`, RED)
    if (existsSync(BIN_DIR)) log(`  • ${BIN_DIR}`, RED)
    log('', RED)
    log('Press Ctrl+C to cancel. Uninstalling in 5 seconds...', YELLOW)
    await new Promise(r => setTimeout(r, 5000))
  }

  // 1. Stop services
  log('Stopping services...')
  if (!isWindows) {
    try {
      execSync('systemctl stop hercules-gateway 2>/dev/null || true', { stdio: 'pipe' })
      execSync('systemctl disable hercules-gateway 2>/dev/null || true', { stdio: 'pipe' })
      execSync('rm -f /etc/systemd/system/hercules-gateway.service', { stdio: 'pipe' })
      execSync('systemctl daemon-reload 2>/dev/null || true', { stdio: 'pipe' })
    } catch {
      // not root or no systemd
    }
    try {
      execSync('launchctl bootout gui/$(id -u)/com.hercules.gateway 2>/dev/null || true', { stdio: 'pipe' })
      execSync(`rm -f ${join(homedir(), 'Library/LaunchAgents/com.hercules.gateway.plist')}`, { stdio: 'pipe' })
    } catch {
      // not macOS
    }
  }

  // 2. Remove PATH entries from shell config
  log('Cleaning PATH entries...')
  if (!isWindows) {
    const home = homedir()
    const rcFiles = [
      join(home, '.zshrc'),
      join(home, '.bashrc'),
      join(home, '.bash_profile'),
      join(home, '.profile'),
    ]

    for (const rcFile of rcFiles) {
      try {
        let content = await readFile(rcFile, 'utf-8')
        const original = content
        content = content.split('\n').filter(line => {
          return !line.includes('HERCULES_HOME') &&
                 !line.includes('HERCULES_BIN') &&
                 !line.includes('.hercules/bin')
        }).join('\n').replace(/\n{3,}/g, '\n\n')
        if (content !== original) {
          await writeFile(rcFile, content)
          log(`  Cleaned ${rcFile}`)
        }
      } catch {
        // file doesn't exist, skip
      }
    }
  }

  // 3. Remove installed directories
  log('Removing files...')
  if (existsSync(HERCULES_HOME)) {
    await rm(HERCULES_HOME, { recursive: true, force: true })
    log(`  Removed ${HERCULES_HOME}`)
  }
  if (existsSync(BIN_DIR)) {
    await rm(BIN_DIR, { recursive: true, force: true })
    log(`  Removed ${BIN_DIR}`)

    // Also clean parent .hercules if empty
    const herculesDir = join(homedir(), '.hercules')
    if (existsSync(herculesDir)) {
      try {
        const { readdir } = await import('node:fs/promises')
        const entries = await readdir(herculesDir)
        if (entries.length === 0) {
          await rm(herculesDir, { recursive: true, force: true })
          log(`  Removed empty ${herculesDir}`)
        }
      } catch {
        // not empty or can't read
      }
    }
  }

  log(`\n${BOLD}Hercules Agent has been removed.${NC}`, GREEN)
  log('Restart your terminal for PATH changes to take effect.', YELLOW)
}

main().catch(err => {
  console.error(`Uninstall failed: ${err.message}`)
  process.exit(1)
})
