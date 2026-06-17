import { createInterface, type Interface } from 'node:readline/promises'
import { stdin as input, stdout as output } from 'node:process'
import { AgentLoop } from '@hercules/core'
import type { AgentConfig, ToolDefinition } from '@hercules/core'
import type { ContextEngine, ModelRouter } from '@hercules/core'
import { readFile, writeFile } from 'node:fs/promises'
import { join } from 'node:path'
import { homedir } from 'node:os'
import { randomUUID } from 'node:crypto'
import { createBootstrap } from './bootstrap.js'
import { logger } from './logger.js'

interface ShellOptions {
  model?: string
  session?: string
  configDir?: string
  stream?: boolean
}

export class HerculesShell {
  private rl: Interface
  private agent: AgentLoop | null = null
  private sessionId: string
  private options: Required<ShellOptions>
  private history: string[] = []
  private historyPath: string
  private toolDefinitions: ToolDefinition[] = []
  private modelRouter!: ModelRouter
  private context!: ContextEngine

  constructor(opts: ShellOptions = {}) {
    const configDir = opts.configDir ?? join(homedir(), '.hercules')
    this.options = {
      model: opts.model ?? 'gpt-4o',
      session: opts.session ?? randomUUID(),
      configDir,
      stream: opts.stream ?? false,
    }
    this.sessionId = this.options.session
    this.historyPath = join(configDir, 'history.json')
    this.rl = createInterface({ input, output, prompt: '🤖 hercules> ' })
  }

  async start(): Promise<void> {
    await this.loadHistory()
    this.printWelcome()

    const { modelRouter, context, toolDefinitions } = await createBootstrap({
      defaultModel: this.options.model,
      sessionId: this.sessionId,
    })
    this.modelRouter = modelRouter
    this.context = context
    this.toolDefinitions = toolDefinitions

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
        logger.info(`Current model: ${this.options.model}`)
        this.rl.prompt()
        continue
      }
      if (trimmed.startsWith('/model ')) {
        this.options.model = trimmed.slice(7).trim()
        logger.info(`Model set to: ${this.options.model}`)
        this.rl.prompt()
        continue
      }
      if (trimmed === '/reset') {
        this.sessionId = randomUUID()
        this.agent = null
        this.context.init(this.sessionId)
        logger.info('Session reset. New session: ' + this.sessionId)
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
        tools: this.toolDefinitions,
        contextConfig: { maxTokens: 200_000, compressionThreshold: 100_000, compressionTarget: 50_000, maxMessages: 100 },
        maxTurns: 5,
        workspaceDir: process.cwd(),
        streaming: this.options.stream,
      }
      this.agent = new AgentLoop(config, this.modelRouter, this.context)
      if (this.options.stream) {
        this.agent.on((event) => {
          if (event.type === 'text_delta') {
            process.stdout.write(event.delta)
          }
        })
      }
    }

    const startTime = performance.now()
    try {
      const result = await this.agent.run(input)
      const elapsed = ((performance.now() - startTime) / 1000).toFixed(2)
      const lastAssistant = [...result.messages].reverse().find(m => m.role === 'assistant')
      const output = lastAssistant?.content ?? '(no response)'
      if (!this.options.stream) {
        console.log(`\n${output}`)
      } else {
        process.stdout.write('\n')
      }
      logger.info(`${elapsed}s (turns: ${result.turns})`)
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err)
      logger.error(msg)
    }
  }

  private printWelcome(): void {
    logger.stdout(`
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
    logger.stdout(`
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
    if (this.history.length === 0) { logger.stdout('(no history)'); return }
    this.history.forEach((h, i) => logger.stdout(`  ${i + 1}. ${h}`))
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
    logger.info('Goodbye!')
  }

  getSessionId(): string { return this.sessionId }
}
