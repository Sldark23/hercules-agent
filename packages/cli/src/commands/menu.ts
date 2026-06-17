import { Command } from 'commander'
import { createInterface } from 'node:readline/promises'
import { stdin as input, stdout as output } from 'node:process'

interface MenuItem {
  key: string
  label: string
  cmd?: string
  submenu?: MenuItem[]
}

const MAIN_ITEMS: MenuItem[] = [
  { key: '1', label: 'Run Agent', cmd: 'exec --interactive' },
  { key: '2', label: 'Interactive Shell', cmd: 'shell' },
  { key: '3', label: 'Configuration >', submenu: [
    { key: 'a', label: 'Setup Wizard (interactive)', cmd: 'setup' },
    { key: 'b', label: 'View Config', cmd: 'config --show' },
    { key: 'c', label: 'Set Provider/Model', cmd: 'setup --auto' },
    { key: 'd', label: 'Gateway Settings', cmd: 'gateway config' },
    { key: 'e', label: 'Install Gateway Service', cmd: 'gateway start --service' },
    { key: 'f', label: 'Reset Config', cmd: 'config --reset' },
    { key: 'g', label: 'Back to Main Menu' },
  ]},
  { key: '4', label: 'Gateway', submenu: [
    { key: 'a', label: 'Start Gateway', cmd: 'gateway start' },
    { key: 'b', label: 'Start as Daemon', cmd: 'gateway start --daemon' },
    { key: 'c', label: 'Stop Gateway', cmd: 'gateway stop' },
    { key: 'd', label: 'Gateway Status', cmd: 'gateway status' },
    { key: 'e', label: 'Back to Main Menu' },
  ]},
  { key: '5', label: 'System Status', cmd: 'status --verbose' },
  { key: '6', label: 'Inspect State', cmd: 'inspect' },
  { key: '7', label: 'Exit' },
]

function printBox(title: string, items: MenuItem[]): void {
  console.log(`\n╔══════════════════════════════════════╗`)
  console.log(`║  ${title.padEnd(35)}║`)
  console.log(`╠══════════════════════════════════════╣`)
  for (const item of items) {
    console.log(`║  ${item.key}. ${item.label.padEnd(35)}║`)
  }
  console.log(`╚══════════════════════════════════════╝`)
}

async function showSubmenu(rl: Interface, title: string, items: MenuItem[], parentRl: Interface): Promise<void> {
  while (true) {
    console.clear()
    printBox(title, items)
    const choice = (await rl.question('Option: ')).trim().toLowerCase()
    const item = items.find(i => i.key === choice)
    if (!item) {
      console.log('Invalid option.')
      await rl.question('Press Enter...')
      continue
    }
    if (item.label === 'Back to Main Menu' || choice === 'q') {
      return
    }
    if (item.cmd) {
      rl.close()
      const { program } = await import('../index.js')
      await program.parseAsync(['node', 'hercules', ...item.cmd.split(' ')])
      // After command finishes, restart from main menu
      const newRl = createInterface({ input, output })
      await showMainMenu(newRl)
      return
    }
  }
}

async function showMainMenu(rl: Interface): Promise<void> {
  while (true) {
    console.clear()
    printBox('Hercules Agent — Main Menu', MAIN_ITEMS)
    const choice = (await rl.question('Option: ')).trim().toLowerCase()

    if (choice === '7' || choice === 'exit' || choice === 'q') {
      console.log('Goodbye!')
      rl.close()
      return
    }

    const item = MAIN_ITEMS.find(i => i.key === choice)
    if (!item) {
      console.log('Invalid option.')
      await rl.question('Press Enter...')
      continue
    }

    if (item.submenu) {
      await showSubmenu(rl, item.label.replace(' >', ''), item.submenu, rl)
    } else if (item.cmd) {
      rl.close()
      const { program } = await import('../index.js')
      await program.parseAsync(['node', 'hercules', ...item.cmd.split(' ')])
      return
    }
  }
}

export const menuCommand = new Command('menu')
  .description('Show interactive main menu')
  .action(async () => {
    const rl = createInterface({ input, output })
    await showMainMenu(rl)
  })
