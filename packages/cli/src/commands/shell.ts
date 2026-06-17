import { Command } from 'commander'
import { HerculesShell } from '../shell.js'

export const shellCommand = new Command('shell')
  .description('Start interactive agent shell')
  .alias('repl')
  .option('-m, --model <id>', 'Model to use', 'gpt-4o')
  .option('-s, --session <id>', 'Session ID (auto-generated if omitted)')
  .action(async (options) => {
    const shell = new HerculesShell({
      model: options.model,
      session: options.session,
    })
    await shell.start()
  })
