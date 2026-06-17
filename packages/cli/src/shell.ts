import { createInterface, type Interface } from 'node:readline/promises'
import { stdin as input, stdout as output } from 'node:process'
import { AgentLoop, ModelRouter, ContextEngine, CredentialPool, getI18n } from '@hercules/core'
import type { AgentConfig } from '@hercules/core'
import { readFile, writeFile } from 'node:fs/promises'
import { join } from 'node:path'
import { homedir } from 'node:os'
import { randomUUID } from 'node:crypto'

interface ShellOptions {
  model?: string
  session?: string
  configDir?: string
}

export class HerculesShell {
  private rl: Interface
  private agent: AgentLoop | null = null
  private sessionId: string
  private options: Required<ShellOptions>
  private history: string[] = []
  private historyPath: string
  private modelRouter: ModelRouter
  private context: ContextEngine

  constructor(opts: ShellOptions = {}) {
    const configDir = opts.configDir ?? join(homedir(), '.hercules')
    this.options = {
      model: opts.model ?? 'gpt-4o',
      session: opts.session ?? randomUUID(),
      configDir,
    }
    this.sessionId = this.options.session
    this.historyPath = join(configDir, 'history.json')
    this.rl = createInterface({ input, output, prompt: '🤖 hercules> ' })
    this.modelRouter = new ModelRouter(new CredentialPool(), {
      defaultModel: this.options.model,
      maxRetries: 3,
    })
    this.context = new ContextEngine({ maxTokens: 200_000 })
    this.context.init(this.sessionId)
  }

  async start(): Promise<void> {
    await this.loadHistory()
    this.printWelcome()
    this.rl.prompt()

    for await (const line of this.rl) {
      const trimmed = line.trim()
      if (!trimmed) { this.rl.prompt(); continue }

      if (trimmed === 'exit' || trimmed === 'quit' || trimmed === '/q') {
        await this.shutdown()
        return
      }
      if (trimmed === '/help' || trimmed === 'help') {
        this.printHelp()
        this.rl.prompt()
        continue
      }
      if (trimmed === '/clear' || trimmed === 'clear') {
        console.clear()
        this.rl.prompt()
        continue
      }
      if (trimmed === '/model') {
        console.log(`Current model: ${this.options.model}`)
        this.rl.prompt()
        continue
      }
      if (trimmed.startsWith('/model ')) {
        this.options.model = trimmed.slice(7).trim()
        console.log(`Model set to: ${this.options.model}`)
        this.rl.prompt()
        continue
      }
      if (trimmed === '/reset') {
        this.sessionId = randomUUID()
        this.agent = null
        this.context.init(this.sessionId)
        console.log('Session reset. New session: ' + this.sessionId)
        this.rl.prompt()
        continue
      }
      if (trimmed === '/history') {
        this.printHistory()
        this.rl.prompt()
        continue
      }

      await this.handleInput(trimmed)
      this.history.push(trimmed)
      this.rl.prompt()
    }
  }

  private async handleInput(input: string): Promise<void> {
    if (!this.agent) {
      const config: AgentConfig = {
        sessionId: this.sessionId,
        modelId: this.options.model,
        systemPrompt: {
          persona: 'You are Hercules, a helpful AI assistant.',
          skills: [],
          constraints: ['Be concise and accurate.'],
        },
        tools: [],
        contextConfig: { maxTokens: 200_000 },
        maxTurns: 5,
        workspaceDir: process.cwd(),
      }
      this.agent = new AgentLoop(config, this.modelRouter, this.context)
    }

    const startTime = performance.now()
    try {
      const result = await this.agent.run(input)
      const elapsed = ((performance.now() - startTime) / 1000).toFixed(2)
      const lastAssistant = [...result.messages].reverse().find(m => m.role === 'assistant')
      const output = lastAssistant?.content ?? '(no response)'
      console.log(`\n${output}`)
      console.log(`\n  ─── ${elapsed}s (turns: ${result.turns}) ───`)
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err)
      console.error(`\nError: ${msg}`)
    }
  }

  private printWelcome(): void {
    console.log(`
╔══════════════════════════════════════════╗
║     Hercules Agent — Interactive Shell   ║
╠══════════════════════════════════════════╣
║  Type a message and press Enter          ║
║  Commands: /model /reset /history /help  ║
║  /clear /exit                            ║
╚══════════════════════════════════════════╝
`)
  }

  private printHelp(): void {
    console.log(`
Commands:
  <text>         Send a message to the agent
  /model         Show current model
  /model <id>    Set model (e.g. /model gpt-4o)
  /reset         Reset conversation
  /history       Show command history
  /clear         Clear screen
  /help          Show this help
  /q, /exit      Quit
`)
  }

  private printHistory(): void {
    if (this.history.length === 0) { console.log('(no history)'); return }
    this.history.forEach((h, i) => console.log(`  ${i + 1}. ${h}`))
  }

  private async loadHistory(): Promise<void> {
    try { this.history = JSON.parse(await readFile(this.historyPath, 'utf-8')) }
    catch { /* ignore */ }
  }

  private async saveHistory(): Promise<void> {
    try { await writeFile(this.historyPath, JSON.stringify(this.history.slice(-100))) }
    catch { /* ignore */ }
  }

  async shutdown(): Promise<void> {
    await this.saveHistory()
    this.rl.close()
    console.log('Goodbye!')
  }

  getSessionId(): string { return this.sessionId }
}
