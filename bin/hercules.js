#!/usr/bin/env node
import { execSync } from 'node:child_process'
import { existsSync } from 'node:fs'
import { resolve, dirname } from 'node:path'
import { fileURLToPath } from 'node:url'

const __dirname = dirname(fileURLToPath(import.meta.url))
const root = resolve(__dirname, '..')

const distEntry = resolve(root, 'packages/cli/dist/index.js')
const srcEntry = resolve(root, 'packages/cli/src/index.ts')

// Prefer compiled dist, fall back to tsx for development
if (existsSync(distEntry)) {
  try {
    execSync(`node "${distEntry}" ` + process.argv.slice(2).join(' '), {
      cwd: root,
      stdio: 'inherit',
      env: { ...process.env, PATH: process.env.PATH },
    })
  } catch {
    process.exit(1)
  }
} else {
  console.error('[hercules] Build not found. Run: pnpm build')
  console.error('[hercules] Falling back to tsx (slow)...')
  try {
    execSync('npx --yes tsx "' + srcEntry + '" ' + process.argv.slice(2).join(' '), {
      cwd: root,
      stdio: 'inherit',
      env: { ...process.env, PATH: process.env.PATH },
    })
  } catch {
    process.exit(1)
  }
}
