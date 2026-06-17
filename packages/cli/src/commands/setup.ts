import { Command } from 'commander'
import { createInterface, type Interface } from 'node:readline/promises'
import { stdin as input, stdout as output } from 'node:process'
import { writeFile, mkdir, readFile } from 'node:fs/promises'
import { existsSync } from 'node:fs'
import { join, dirname } from 'node:path'
import { homedir, platform } from 'node:os'
import { fileURLToPath } from 'node:url'
import { execSync, spawn } from 'node:child_process'
import { createProviderPresets } from '@hercules/core'

const __dirname = dirname(fileURLToPath(import.meta.url))
const HERCULES_DIR = join(homedir(), '.hercules')
const GATEWAY_CONFIG = join(HERCULES_DIR, 'gateway.json')
const AGENT_CONFIG = join(HERCULES_DIR, 'config.json')
const SCRIPTS_DIR = join(__dirname, '..', '..', '..', '..', 'scripts')

const BOLD = '\x1b[1m'
const GREEN = '\x1b[32m'
const YELLOW = '\x1b[33m'
const CYAN = '\x1b[36m'
const MAGENTA = '\x1b[35m'
const NC = '\x1b[0m'

const PROVIDERS = createProviderPresets()

function showProviderMenu(): void {
  console.log(`\n${CYAN}╔════════════════════════════════════════════════════════════════════╗${NC}`)
  console.log(`${CYAN}║                    AVAILABLE LLM PROVIDERS                      ║${NC}`)
  console.log(`${CYAN}╠════════════════════════════════════════════════════════════════════╗${NC}`)

  PROVIDERS.forEach((p: any, i: number) => {
    const num = String(i + 1).padStart(2, ' ')
    const name = p.id.padEnd(15)
    const model = (p.defaultModel ?? '?').padEnd(30)
    console.log(`${CYAN}║  ${num}) ${MAGENTA}${name}${NC} ${CYAN}${model}║${NC}`)
  })

  console.log(`${CYAN}╠════════════════════════════════════════════════════════════════════╣${NC}`)
  console.log(`${CYAN}║  ${YELLOW}Local:${NC} ollama, local              ${CYAN}                            ║${NC}`)
  console.log(`${CYAN}║  ${YELLOW}Cloud:${NC} openai, anthropic, google, deepseek, groq, etc   ║${NC}`)
  console.log(`${CYAN}╚════════════════════════════════════════════════════════════════════╝${NC}\n`)
}

function ask(rl: Interface, question: string, defaultVal = ''): Promise<string> {
  const def = defaultVal ? ` (${defaultVal})` : ''
  return rl.question(`${question}${def}: `)
}

async function promptYesNo(rl: Interface, question: string): Promise<boolean> {
  const answer = (await rl.question(`${question} (Y/n): `)).trim().toLowerCase()
  return answer !== 'n' && answer !== 'no'
}

export const setupCommand = new Command('setup')
  .description('Interactive first-time setup for Hercules Agent')
  .option('--auto', 'Non-interactive setup with defaults')
  .option('--skip-service', 'Skip service installation')
  .action(async (options) => {
    const auto = options.auto ?? false
    const skipService = options.skipService ?? false
    
    await mkdir(HERCULES_DIR, { recursive: true })
    await mkdir(join(HERCULES_DIR, 'logs'), { recursive: true })

    if (auto) {
      await autoSetup()
      return
    }

    await interactiveSetup(skipService)
  })

async function autoSetup() {
  console.log(`${BOLD}[setup] Running automatic setup...${NC}`)

  // Default config
  await writeFile(AGENT_CONFIG, JSON.stringify({
    defaultModel: 'gpt-4o',
    provider: 'openai',
    workspaceDir: process.cwd(),
    theme: 'dark',
  }, null, 2))

  await writeFile(GATEWAY_CONFIG, JSON.stringify({
    host: '0.0.0.0',
    port: 3000,
    authToken: crypto.randomUUID(),
    allowedOrigins: ['*'],
  }, null, 2))

  console.log(`${GREEN}[setup] Configuration files created.${NC}`)
  console.log(`${GREEN}[setup] Run 'hercules menu' to start.${NC}`)
}

async function interactiveSetup(skipService: boolean) {
  const rl = createInterface({ input, output })

  console.clear()
  console.log(`
${BOLD}╔════════════════════════════════════════╗
║     Hercules Agent — Setup Wizard      ║
╠════════════════════════════════════════╣
║  Let's configure your agent.          ║
║  Press Enter to accept defaults.      ║
╚════════════════════════════════════════╝${NC}
`)

  showProviderMenu()

  // 1. Provider
  console.log(`${CYAN}── LLM Provider ──${NC}`)
  const providerInput = (await rl.question('Select provider (number or name): ')).trim()
  let provider: string
  let model: string

  const providerNum = parseInt(providerInput, 10)
  if (!isNaN(providerNum) && providerNum > 0 && providerNum <= PROVIDERS.length) {
    const selected = PROVIDERS[providerNum - 1]!
    provider = selected.id
    model = selected.defaultModel ?? 'gpt-4o'
  } else {
    provider = providerInput || 'openai'
    const selected = PROVIDERS.find((p: any) => p.id === provider)
    model = selected?.defaultModel ?? 'gpt-4o'
  }

  console.log(`  ${GREEN}Provider: ${provider}${NC}`)
  const modelInputAnswer = (await rl.question('Default model')).trim() || model || 'gpt-4o'
  model = modelInputAnswer

  const apiKeyEnv = provider === 'anthropic' ? 'ANTHROPIC_API_KEY' 
    : provider === 'google' ? 'GOOGLE_API_KEY'
    : provider === 'ollama' ? 'OLLAMA_BASE_URL'
    : 'OPENAI_API_KEY'
  const apiKey = (await rl.question(`API key for ${provider} (optional): `)).trim()

  if (apiKey) {
    process.env[apiKeyEnv] = apiKey
    const envFile = join(HERCULES_DIR, '.env')
    let envContent = ''
    if (existsSync(envFile)) {
      envContent = await readFile(envFile, 'utf-8')
    }
    envContent += `${apiKeyEnv}=${apiKey}\n`
    await writeFile(envFile, envContent)
    console.log(`  ${GREEN}Saved to ${envFile}${NC}`)
  }

  await writeFile(AGENT_CONFIG, JSON.stringify({
    defaultModel: model,
    provider,
    workspaceDir: process.cwd(),
    theme: 'dark',
  }, null, 2))

  // 2. Gateway
  console.log(`\n${CYAN}── Gateway ──${NC}`)
  const enableGateway = await promptYesNo(rl, 'Enable HTTP gateway?')
  let gatewayPort = 3000
  let authToken: string = crypto.randomUUID()

  if (enableGateway) {
    gatewayPort = parseInt((await ask(rl, 'Port', '3000')).trim() || '3000', 10)
    authToken = (await ask(rl, 'Auth token (empty = auto-generate)')).trim() || crypto.randomUUID()

    await writeFile(GATEWAY_CONFIG, JSON.stringify({
      host: '0.0.0.0',
      port: gatewayPort,
      authToken,
      allowedOrigins: ['*'],
    }, null, 2))
    console.log(`  ${GREEN}Gateway config saved. Auth token: ${authToken.slice(0, 8)}...${NC}`)

    if (!skipService) {
      const installService = await promptYesNo(rl, `Install gateway as system service (${platform() === 'linux' ? 'systemd' : platform() === 'darwin' ? 'launchd' : 'Windows'} service)?`)
      if (installService) {
        await installSystemService()
      }
    }
  } else {
    await writeFile(GATEWAY_CONFIG, JSON.stringify({ enabled: false }, null, 2))
  }

  // 3. Summary
  const fullToken = apiKey.slice(0, 8)
  console.log(`\n${GREEN}${BOLD}── Setup Complete ──${NC}`)
  console.log(`  Provider:     ${provider}`)
  console.log(`  Model:        ${model}`)
  console.log(`  API Key:      ${apiKey ? fullToken + '...' : '(not set)'}`)
  console.log(`  Gateway:      ${enableGateway ? `port ${gatewayPort}` : 'disabled'}`)
  console.log(`  Config dir:   ${HERCULES_DIR}`)
  console.log(`\n${BOLD}Run 'hercules menu' to start the agent.${NC}`)
  console.log(`Or 'hercules gateway start' to launch the gateway.\n`)

  rl.close()
}

async function installSystemService() {
  const os = platform()
  try {
    if (os === 'linux') {
      const svcScript = join(SCRIPTS_DIR, 'install-service.sh')
      if (existsSync(svcScript)) {
        execSync(`sudo bash "${svcScript}"`, { stdio: 'inherit' })
      } else {
        console.log(`${YELLOW}Service script not found. Install manually:${NC}`)
        console.log(`  sudo bash ${SCRIPTS_DIR}/install-service.sh`)
      }
    } else if (os === 'darwin') {
      const svcScript = join(SCRIPTS_DIR, 'install-service.sh')
      if (existsSync(svcScript)) {
        execSync(`bash "${svcScript}"`, { stdio: 'inherit' })
      } else {
        console.log(`${YELLOW}Service script not found. Install manually:${NC}`)
        console.log(`  bash ${SCRIPTS_DIR}/install-service.sh`)
      }
    } else if (os === 'win32') {
      console.log(`${YELLOW}Windows: use NSSM to install as service:${NC}`)
      console.log(`  nssm install HerculesGateway "node" "${join(HERCULES_DIR, 'agent', 'packages', 'gateway', 'dist', 'daemon.js')}"`)
    }
    console.log(`${GREEN}Service installed.${NC}`)
  } catch (err) {
    console.log(`${YELLOW}Service installation skipped (${err instanceof Error ? err.message : 'unknown error'}).${NC}`)
  }
}
