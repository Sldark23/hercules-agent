import { Command } from 'commander'
import { AgentLoop } from '@hercules/core'
import { randomUUID } from 'node:crypto'
import { createBootstrap } from '../bootstrap.js'
import { logger } from '../logger.js'

export const execCommand = new Command('exec')
  .description('Run a single agent interaction')
  .argument('[input]', 'User input prompt (omit for stdin)')
  .option('-m, --model <id>', 'Model ID to use', 'gpt-4o')
  .option('-s, --session <id>', 'Session ID (auto-generated if omitted)')
  .option('-t, --max-turns <n>', 'Maximum turns', '5')
  .option('-w, --workspace <dir>', 'Workspace directory', process.cwd())
  .option('-i, --interactive', 'Read input from stdin until EOF')
  .option('--stream', 'Enable streaming response output')
  .action(async (input, options) => {
    const sessionId = options.session ?? randomUUID()
    const { modelRouter, context, toolDefinitions } = await createBootstrap({
      defaultModel: options.model,
      sessionId,
      workspaceDir: options.workspace,
    })

    const agent = new AgentLoop({
      sessionId,
      modelId: options.model,
      systemPrompt: {
        persona: 'You are Hercules, a helpful AI assistant.',
        skills: [],
        constraints: ['Be concise and accurate.'],
      },
      tools: toolDefinitions,
      contextConfig: { maxTokens: 200_000, compressionThreshold: 100_000, compressionTarget: 50_000, maxMessages: 100 },
      maxTurns: parseInt(options.maxTurns, 10),
      workspaceDir: options.workspace,
      streaming: options.stream ?? false,
    }, modelRouter, context)

    const processInput = async (text: string) => {
      logger.info(`Running (model=${options.model}, session=${sessionId.slice(0, 8)})`)
      const startTime = performance.now()

      if (options.stream) {
        let buffer = ''
        agent.on((event) => {
          if (event.type === 'text_delta') {
            process.stdout.write(event.delta)
            buffer += event.delta
          }
        })
        try {
          const result = await agent.run(text)
          const elapsed = ((performance.now() - startTime) / 1000).toFixed(2)
          if (!buffer) {
            const lastAssistant = [...result.messages].reverse().find(m => m.role === 'assistant')
            if (lastAssistant?.content) logger.stdout(lastAssistant.content)
          }
          process.stdout.write('\n')
          logger.info(`${elapsed}s (turns: ${result.turns})`, { elapsed, turns: result.turns })
        } catch (err) {
          const msg = err instanceof Error ? err.message : String(err)
          logger.error(msg)
          process.exit(1)
        }
        return
      }

      try {
        const result = await agent.run(text)
        const elapsed = ((performance.now() - startTime) / 1000).toFixed(2)
        const lastAssistant = [...result.messages].reverse().find(m => m.role === 'assistant')
        if (lastAssistant?.content) {
          logger.stdout(lastAssistant.content)
        } else if (result.error) {
          logger.error(result.error)
        } else {
          logger.stdout('(no response)')
        }
        logger.info(`${elapsed}s (turns: ${result.turns})`, { elapsed, turns: result.turns })
      } catch (err) {
        const msg = err instanceof Error ? err.message : String(err)
        logger.error(msg)
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
      logger.error('No input provided. Pass as argument or use --interactive for stdin.')
      logger.error('  hercules exec "your prompt"')
      logger.error('  echo "prompt" | hercules exec --interactive')
      process.exit(1)
    }
  })
