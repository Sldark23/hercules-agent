import { Command } from 'commander'
import { spawn, execSync } from 'node:child_process'
import { readFile, access } from 'node:fs/promises'
import { join } from 'node:path'
import { logger } from '../logger.js'

const REMOTE = 'Sldark23/hercules-agent'
const GIT_REMOTE = 'origin'
const GIT_BRANCH = 'main'

interface UpdateInfo {
  currentCommit: string
  latestCommit: string
  behind: number
  ahead: number
  usingGit: boolean
}

async function getGitRoot(): Promise<string | null> {
  try {
    const out = execSync('git rev-parse --show-toplevel', { encoding: 'utf-8', timeout: 5000 }).trim()
    return out
  } catch {
    return null
  }
}

async function checkGitUpdate(root: string): Promise<UpdateInfo | null> {
  try {
    execSync(`git fetch ${GIT_REMOTE} ${GIT_BRANCH}`, { cwd: root, timeout: 15000, stdio: 'pipe' })
    const currentCommit = execSync('git rev-parse HEAD', { cwd: root, encoding: 'utf-8', timeout: 5000 }).trim()
    const latestCommit = execSync(`git rev-parse ${GIT_REMOTE}/${GIT_BRANCH}`, { cwd: root, encoding: 'utf-8', timeout: 5000 }).trim()
    const behind = Number(execSync(`git rev-list --count HEAD..${GIT_REMOTE}/${GIT_BRANCH}`, { cwd: root, encoding: 'utf-8', timeout: 5000 }).trim())
    const ahead = Number(execSync(`git rev-list --count ${GIT_REMOTE}/${GIT_BRANCH}..HEAD`, { cwd: root, encoding: 'utf-8', timeout: 5000 }).trim())
    return { currentCommit: currentCommit.slice(0, 7), latestCommit: latestCommit.slice(0, 7), behind, ahead, usingGit: true }
  } catch {
    return null
  }
}

async function checkApiUpdate(): Promise<UpdateInfo | null> {
  try {
    const res = await fetch(`https://api.github.com/repos/${REMOTE}/commits/main`, {
      headers: { Accept: 'application/vnd.github.v3.sha', 'User-Agent': 'hercules-agent' },
    })
    if (!res.ok) return null
    const latestCommit = (await res.text()).trim().slice(0, 7)

    const localCommit = await getLocalCommit()
    if (!localCommit) return { currentCommit: 'unknown', latestCommit, behind: -1, ahead: 0, usingGit: false }

    const compare = await fetch(`https://api.github.com/repos/${REMOTE}/compare/${localCommit}...main`, {
      headers: { Accept: 'application/vnd.github.v3+json', 'User-Agent': 'hercules-agent' },
    })
    if (!compare.ok) return { currentCommit: localCommit, latestCommit, behind: -1, ahead: 0, usingGit: false }
    const data = (await compare.json()) as { behind_by: number; ahead_by: number }
    return { currentCommit: localCommit, latestCommit, behind: data.behind_by, ahead: data.ahead_by, usingGit: false }
  } catch {
    return null
  }
}

async function getLocalCommit(): Promise<string | null> {
  const root = await getGitRoot()
  if (!root) return null
  try {
    const out = execSync('git rev-parse HEAD', { cwd: root, encoding: 'utf-8', timeout: 5000 }).trim()
    return out.slice(0, 7)
  } catch {
    return null
  }
}

async function doUpdate(root: string): Promise<boolean> {
  try {
    logger.info('Pulling latest...')
    execSync(`git pull ${GIT_REMOTE} ${GIT_BRANCH}`, { cwd: root, timeout: 30000, stdio: 'inherit' })
    logger.info('Rebuilding...')
    execSync('pnpm install --frozen-lockfile', { cwd: root, timeout: 60000, stdio: 'inherit' })
    execSync('pnpm build', { cwd: root, timeout: 120000, stdio: 'inherit' })
    logger.info('Update complete!')
    return true
  } catch (err) {
    logger.error(`Update failed: ${err instanceof Error ? err.message : err}`)
    return false
  }
}

export const updateCommand = new Command('update')
  .description(`Check for updates from github.com/${REMOTE}`)
  .option('-c, --check', 'Only check, do not update')
  .option('-y, --yes', 'Auto-confirm update')
  .action(async (options) => {
    const root = await getGitRoot()
    let info: UpdateInfo | null = null

    if (root) {
      info = await checkGitUpdate(root)
    }
    if (!info) {
      logger.info('Git not available, falling back to GitHub API...')
      info = await checkApiUpdate()
    }
    if (!info) {
      logger.error('Could not check for updates')
      process.exit(1)
    }

    logger.info(`Current:  ${info.currentCommit}`)
    logger.info(`Latest:   ${info.latestCommit}`)

    if (info.behind < 0) {
      logger.info('Could not determine behind count (install via git clone?)')
      return
    }

    if (info.behind === 0 && info.ahead === 0) {
      logger.info('Up to date')
      return
    }

    logger.info(`Behind:   ${info.behind} commit${info.behind !== 1 ? 's' : ''}`)
    if (info.ahead > 0) {
      logger.info(`Ahead:    ${info.ahead} commit${info.ahead !== 1 ? 's' : ''} (local changes)`)
    }

    if (info.behind > 0 && !options.check) {
      if (!root) {
        logger.error('Cannot auto-update: not a git repository. Run install.js again')
        return
      }
      if (info.ahead > 0) {
        logger.error('Cannot auto-update: local changes detected. Commit or stash them first')
        return
      }
      if (options.yes) {
        await doUpdate(root)
      } else {
        process.stdout.write('[hercules] Update now? [Y/n] ')
        const answer = await new Promise<string>((resolve) => {
          process.stdin.once('data', (data) => resolve(data.toString().trim().toLowerCase()))
        })
        if (answer === '' || answer === 'y' || answer === 'yes') {
          await doUpdate(root)
        }
      }
    }
  })
