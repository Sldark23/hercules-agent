import { Command } from 'commander'
import { AgentLoop, ModelRouter, ContextEngine, CredentialPool } from '@hercules/core'
import type { AgentConfig } from '@hercules/core'
import { randomUUID } from 'node:crypto'

export const execCommand = new Command('exec')
  .description('Run a single agent interaction')
  .argument('[input]', 'User input prompt (omit for stdin)')
  .option('-m, --model <id>', 'Model ID to use', 'gpt-4o')
  .option('-s, --session <id>', 'Session ID (auto-generated if omitted)')
  .option('-t, --max-turns <n>', 'Maximum turns', '5')
  .option('-w, --workspace <dir>', 'Workspace directory', process.cwd())
  .option('-i, --interactive', 'Read input from stdin until EOF')
  .action(async (input, options) => {
    const sessionId = options.session ?? randomUUID()
    const modelRouter = new ModelRouter(new CredentialPool(), {
      defaultModel: options.model,
      maxRetries: 3,
    })
    const context = new ContextEngine({ maxTokens: 200_000 })
    context.init(sessionId)

    const agent = new AgentLoop({
      sessionId,
      modelId: options.model,
      systemPrompt: {
        persona: 'You are Hercules, a helpful AI assistant.',
        skills: [],
        constraints: ['Be concise and accurate.'],
      },
      tools: [],
      contextConfig: { maxTokens: 200_000 },
      maxTurns: parseInt(options.maxTurns, 10),
      workspaceDir: options.workspace,
    }, modelRouter, context)

    const processInput = async (text: string) => {
      console.error(`[hercules] Running (model=${options.model}, session=${sessionId.slice(0, 8)})`)
      const startTime = performance.now()
      try {
        const result = await agent.run(text)
        const elapsed = ((performance.now() - startTime) / 1000).toFixed(2)
        const lastAssistant = [...result.messages].reverse().find(m => m.role === 'assistant')
        if (lastAssistant?.content) {
          console.log(lastAssistant.content)
        } else if (result.error) {
          console.error(`Error: ${result.error}`)
        } else {
          console.log('(no response)')
        }
        console.error(`\n  ─── ${elapsed}s (turns: ${result.turns}) ───`)
      } catch (err) {
        const msg = err instanceof Error ? err.message : String(err)
        console.error(`Error: ${msg}`)
        process.exit(1)
      }
    }

    if (input) {
      await processInput(input)
    } else if (options.interactive) {
      const chunks: string[] = []
      for await (const chunk of process.stdin) {
        chunks.push(chunk.toString())
      }
      await processInput(chunks.join('').trim())
    } else {
      console.error('No input provided. Pass as argument or use --interactive for stdin.')
      console.error('  hercules exec "your prompt"')
      console.error('  echo "prompt" | hercules exec --interactive')
      process.exit(1)
    }
  })
