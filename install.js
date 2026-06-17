#!/usr/bin/env node
/**
 * Hercules Agent — Universal Node.js installer
 * Works on: Linux, macOS, Windows (via Node.js)
 */
import { execSync } from 'node:child_process'
import { existsSync, mkdirSync } from 'node:fs'
import { readFile, writeFile, mkdir, cp, rm, readdir } from 'node:fs/promises'
import { homedir, platform } from 'node:os'
import { join, dirname } from 'node:path'
import { fileURLToPath } from 'node:url'

const __dirname = dirname(fileURLToPath(import.meta.url))
const isWindows = platform() === 'win32'

const HERCULES_HOME = process.env.HERCULES_HOME || join(homedir(), '.hercules', 'agent')
const BIN_DIR = process.env.HERCULES_BIN || join(homedir(), '.hercules', 'bin')
const GIT_REPO = process.env.HERCULES_REPO || 'https://github.com/Sldark23/hercules-agent.git'
const VERSION = '0.1.0'

const BOLD = '\x1b[1m'
const GREEN = '\x1b[32m'
const YELLOW = '\x1b[33m'
const RED = '\x1b[31m'
const DIM = '\x1b[2m'
const NC = '\x1b[0m'

function log(msg, color = GREEN) { console.log(`${color}${msg}${NC}`) }

function step(msg) { console.log(`\n${BOLD}==>${NC} ${msg}...`) }

function exec(cmd, opts = {}) {
  console.log(`${DIM}> ${cmd}${NC}`)
  try {
    execSync(cmd, { stdio: 'inherit', ...opts })
  } catch (err) {
    throw new Error(`Command failed: ${cmd}\n  ${err.message}`)
  }
}

function showHelp() {
  console.log(`${BOLD}Hercules Agent Installer${NC} v${VERSION}
${DIM}────────────────────────────────────────${NC}
${BOLD}Usage:${NC}
  node install.js              Run installer
  node install.js --help       Show this help
  node install.js --version    Show version

${BOLD}Environment variables:${NC}
  HERCULES_HOME    Install directory (default: ~/.hercules/agent)
  HERCULES_BIN     Binary directory (default: ~/.hercules/bin)
  HERCULES_REPO    Git repository URL (default: GitHub)
`)
}

async function main() {
  const args = process.argv.slice(2)

  if (args.includes('--help') || args.includes('-h')) {
    showHelp()
    return
  }

  if (args.includes('--version') || args.includes('-v')) {
    console.log(VERSION)
    return
  }

  log(`\n${BOLD}Hercules Agent Installer v${VERSION}${NC}\n`, GREEN)

  // 1. Check Node.js version
  step('Checking Node.js')
  const nodeVer = parseInt(process.version.slice(1).split('.')[0], 10)
  if (nodeVer < 22) {
    log(`Node.js >= 22 required (found ${process.version})`, RED)
    process.exit(1)
  }
  log(`  Node.js ${process.version} — OK`)

  // 2. Ensure pnpm
  step('Checking pnpm')
  try {
    execSync('pnpm --version', { stdio: 'pipe' })
  } catch {
    log('  pnpm not found. Installing via npm...', YELLOW)
    exec('npm install -g pnpm')
  }
  const pnpmVer = execSync('pnpm --version', { encoding: 'utf-8' }).trim()
  log(`  pnpm ${pnpmVer} — OK`)

  // 3. Copy or update project files
  step('Setting up project files')
  if (existsSync(HERCULES_HOME)) {
    log(`  Found existing install at ${HERCULES_HOME}`, YELLOW)
    process.chdir(HERCULES_HOME)
    try {
      exec('git pull --rebase', { stdio: 'pipe' })
      log('  Updated via git pull')
    } catch {
      log('  Not a git repo or git unavailable. Copying fresh copy...', YELLOW)
      const tmpDir = join(HERCULES_HOME, '.hercules-tmp')
      await rm(tmpDir, { recursive: true, force: true })
      await mkdir(tmpDir, { recursive: true })
      await cp(__dirname, tmpDir, {
        recursive: true,
        filter: (src) => !src.includes('node_modules') && !src.includes('.hercules-tmp')
      })
      for (const entry of await readdir(tmpDir)) {
        const src = join(tmpDir, entry)
        const dest = join(HERCULES_HOME, entry)
        await rm(dest, { recursive: true, force: true })
        await cp(src, dest, { recursive: true })
      }
      await rm(tmpDir, { recursive: true, force: true })
    }
  } else {
    log(`  Installing to ${HERCULES_HOME}`)
    try {
      exec(`git clone ${GIT_REPO} "${HERCULES_HOME}"`, { stdio: 'pipe' })
      log('  Cloned from repository')
    } catch {
      log('  Git clone failed. Copying local files...', YELLOW)
      mkdirSync(HERCULES_HOME, { recursive: true })
      await cp(__dirname, HERCULES_HOME, {
        recursive: true,
        filter: (src) => !src.includes('node_modules')
      })
    }
    process.chdir(HERCULES_HOME)
  }

  // 4. Install deps & build
  step('Installing dependencies')
  exec('pnpm install')

  step('Building packages')
  exec('pnpm build')

  // 5. Create bin wrappers
  step('Creating binary wrappers')
  mkdirSync(BIN_DIR, { recursive: true })

  if (isWindows) {
    const batchContent = `@echo off
set HERCULES_HOME=%HERCULES_HOME%
if "%HERCULES_HOME%"=="" set HERCULES_HOME=${HERCULES_HOME.replace(/\//g, '\\')}
node "%HERCULES_HOME%\\packages\\cli\\dist\\index.js" %*
`
    await writeFile(join(BIN_DIR, 'hercules.cmd'), batchContent)
    log('  Created hercules.cmd wrapper')

    const psContent = `$env:HERCULES_HOME = if ($env:HERCULES_HOME) { $env:HERCULES_HOME } else { '${HERCULES_HOME.replace(/\//g, '\\')}' }
node "$env:HERCULES_HOME\\packages\\cli\\dist\\index.js" $args
`
    await writeFile(join(BIN_DIR, 'hercules.ps1'), psContent)
    log('  Created hercules.ps1 wrapper')
  } else {
    const shContent = `#!/usr/bin/env bash
export HERCULES_HOME="${HERCULES_HOME}"
exec node "${HERCULES_HOME}/packages/cli/dist/index.js" "$@"
`
    const binPath = join(BIN_DIR, 'hercules')
    await writeFile(binPath, shContent)
    execSync(`chmod +x "${binPath}"`)
    log(`  Created hercules wrapper at ${binPath}`)
  }

  // 6. Add to PATH
  step('Setting up PATH')
  if (isWindows) {
    const userPath = execSync('echo %PATH%', { encoding: 'utf-8', shell: 'cmd.exe' }).trim()
    if (!userPath.includes(BIN_DIR)) {
      try {
        execSync(`setx Path "%Path%;${BIN_DIR}"`, { stdio: 'pipe' })
        log('  Added to PATH via setx')
        log('  Restart your terminal to use the hercules command.', YELLOW)
      } catch {
        log('  Could not auto-add to PATH.', YELLOW)
        log(`  Run manually: setx Path "%Path%;${BIN_DIR}"`, YELLOW)
      }
    } else {
      log('  Already in PATH')
    }
  } else {
    const shellPath = process.env.SHELL || ''
    const home = homedir()
    let rcFile = ''
    if (shellPath.includes('zsh')) {
      rcFile = join(home, '.zshrc')
    } else if (shellPath.includes('bash')) {
      rcFile = join(home, '.bashrc')
    } else {
      rcFile = join(home, '.profile')
    }

    let rcContent = ''
    try {
      rcContent = await readFile(rcFile, 'utf-8')
    } catch {
      rcContent = ''
    }

    if (!rcContent.includes('HERCULES_BIN')) {
      const pathEntry = `\n# Hercules Agent\nexport HERCULES_HOME="\${HERCULES_HOME:-${HERCULES_HOME}}"\nexport PATH="${BIN_DIR}:$PATH"\n`
      await writeFile(rcFile, rcContent + pathEntry)
      log(`  Added to PATH in ${rcFile}`)
      log(`  Run: source ${rcFile}`, YELLOW)
    } else {
      log('  Already configured in shell config')
    }
  }

  // 7. Run setup
  step('Running initial setup')
  try {
    execSync(`node "${HERCULES_HOME}/packages/cli/dist/index.js" setup --auto`, { stdio: 'inherit' })
  } catch {
    log('  Setup wizard failed. Run manually: hercules setup', YELLOW)
  }

  // 8. Done
  log('\n────────────────────────────────────', GREEN)
  log(`${BOLD}Hercules Agent v${VERSION} installed!${NC}`, GREEN)
  log(`  Location: ${HERCULES_HOME}`, GREEN)
  log(`  Binary:   ${BIN_DIR}`, GREEN)
  log('────────────────────────────────────', GREEN)
  log('\nRun: hercules menu')
  log('Or:  hercules setup')
}

main().catch(err => {
  log(`\nInstallation failed: ${err.message}`, RED)
  process.exit(1)
})
