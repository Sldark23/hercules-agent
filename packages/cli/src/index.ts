#!/usr/bin/env node
import { Command } from 'commander'
import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { execCommand } from './commands/exec.js'
import { configCommand } from './commands/config.js'
import { statusCommand } from './commands/status.js'
import { inspectCommand } from './commands/inspect.js'
import { shellCommand } from './commands/shell.js'
import { menuCommand } from './commands/menu.js'
import { gatewayCommand } from './commands/gateway.js'
import { setupCommand } from './commands/setup.js'
import { updateCommand } from './commands/update.js'

let pkgVersion = '0.1.0'
try {
  const raw = readFileSync(join(import.meta.dirname, '..', 'package.json'), 'utf-8')
  pkgVersion = JSON.parse(raw).version ?? pkgVersion
} catch {}

const program = new Command()

program
  .name('hercules')
  .description('Hercules Agent — Self-improving AI agent with multi-platform gateway')
  .version(pkgVersion)

program.addCommand(execCommand)
program.addCommand(configCommand)
program.addCommand(statusCommand)
program.addCommand(inspectCommand)
program.addCommand(shellCommand)
program.addCommand(menuCommand)
program.addCommand(gatewayCommand)
program.addCommand(setupCommand)
program.addCommand(updateCommand)

if (process.env.VITEST !== 'true') {
  if (process.argv.length <= 2) {
    void menuCommand.parseAsync(['node', 'hercules', 'menu'])
  } else {
    program.parse(process.argv)
  }
}

export { program }
