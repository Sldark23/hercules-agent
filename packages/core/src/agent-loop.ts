import type {
  AgentConfig, AgentTurnResult, AgentState, AgentEvent, AgentEventHandler,
  Message, ToolCall, ToolResult, ToolDefinition, ModelRequest, ThinkingLevel,
} from './types.js'
import { ModelRouter } from './model-router.js'
import { ContextEngine } from './context-engine.js'
import { assembleSystemPrompt } from './system-prompt.js'

export class AgentLoop {
  private config: AgentConfig
  private modelRouter: ModelRouter
  private context: ContextEngine
  private state: AgentState = 'idle'
  private turnCount = 0
  private handlers: AgentEventHandler[] = []
  private abortController: AbortController = new AbortController()
  private thinkingLevel: ThinkingLevel = 'medium'

  constructor(
    config: AgentConfig,
    modelRouter: ModelRouter,
    context: ContextEngine
  ) {
    this.config = config
    this.modelRouter = modelRouter
    this.context = context
    this.context.init(config.sessionId)
  }

  on(handler: AgentEventHandler): () => void {
    this.handlers.push(handler)
    return () => {
      this.handlers = this.handlers.filter(h => h !== handler)
    }
  }

  async run(userInput: string): Promise<AgentTurnResult> {
    this.abortController = new AbortController()
    this.turnCount = 0
    this.state = 'thinking'

    const userMessage: Message = {
      id: crypto.randomUUID(),
      role: 'user',
      content: userInput,
      createdAt: new Date(),
    }
    await this.context.addMessage(this.config.sessionId, userMessage)

    try {
      while (this.turnCount < this.config.maxTurns) {
        this.turnCount++
        this.state = 'thinking'
        await this.emit({ type: 'state_change', state: 'thinking' })

        const response = await this.callModel()

        await this.context.addMessage(this.config.sessionId, {
          id: response.id,
          role: 'assistant',
          content: response.content,
          toolCalls: response.toolCalls,
          createdAt: new Date(),
        })

        if (response.finishReason === 'stop' || response.finishReason === 'max_tokens') {
          if (response.content) {
            await this.emit({ type: 'text_done', text: response.content })
          }
          this.state = 'done'
          break
        }

        if (response.toolCalls && response.toolCalls.length > 0) {
          this.state = 'waiting_tool'
          await this.emit({ type: 'state_change', state: 'waiting_tool' })

          for (const tc of response.toolCalls) {
            await this.emit({ type: 'tool_call', toolCall: tc })
            const result = await this.executeTool(tc)
            await this.emit({ type: 'tool_result', result })
          }
        }
      }

      if (this.turnCount >= this.config.maxTurns) {
        this.state = 'done'
      }

      const messages = this.context.getState(this.config.sessionId)?.messages ?? []
      const usage = this.context.usageSince(this.config.sessionId, new Date(0))

      const result: AgentTurnResult = {
        sessionId: this.config.sessionId,
        messages,
        usage,
        turns: this.turnCount,
        finishedReason: this.turnCount >= this.config.maxTurns ? 'max_turns' : 'completed',
      }

      await this.emit({ type: 'done', result })
      return result

    } catch (err) {
      this.state = 'error'
      const errorMsg = (err as Error).message
      await this.emit({ type: 'error', error: errorMsg })

      return {
        sessionId: this.config.sessionId,
        messages: this.context.getState(this.config.sessionId)?.messages ?? [],
        usage: { input: 0, output: 0 },
        turns: this.turnCount,
        finishedReason: 'error',
        error: errorMsg,
      }
    }
  }

  cancel(): void {
    this.abortController.abort()
    this.state = 'error'
  }

  getState(): AgentState {
    return this.state
  }

  private async callModel() {
    const state = this.context.getState(this.config.sessionId)
    if (!state) throw new Error('Session not initialized')

    const { system } = assembleSystemPrompt(
      this.config.systemPrompt,
      this.config.tools,
      state.messages
    )

    const toolsForModel = this.config.tools.filter(t => {
      return state.messages.filter(m => m.role === 'assistant')
        .every(m => !m.toolCalls?.some(tc => tc.name === t.name))
    })

    const request: ModelRequest = {
      model: this.config.modelId,
      messages: state.messages.slice(-20).map(m => ({
        role: m.role,
        content: m.content,
      })),
      system,
      tools: toolsForModel.length > 0 ? toolsForModel : undefined,
      maxTokens: 4096,
      temperature: 0.7,
      streaming: false,
      thinking: this.thinkingLevel,
      signal: this.abortController.signal,
    }

    return this.modelRouter.call(request)
  }

  private async executeTool(tc: ToolCall): Promise<ToolResult> {
    const tool = this.config.tools.find(t => t.name === tc.name)
    if (!tool) {
      return {
        toolCallId: tc.id,
        output: `Error: Tool "${tc.name}" not found`,
        isError: true,
      }
    }

    try {
      const result = await tool.handler(tc.arguments, {
        sessionId: this.config.sessionId,
        userId: this.config.userId,
        workspaceDir: this.config.workspaceDir,
        env: {},
        abortSignal: this.abortController.signal,
      })

      await this.context.addMessage(this.config.sessionId, {
        id: crypto.randomUUID(),
        role: 'tool',
        content: result.output,
        toolResult: result,
        createdAt: new Date(),
      })

      return result
    } catch (err) {
      const errorResult: ToolResult = {
        toolCallId: tc.id,
        output: `Error: ${(err as Error).message}`,
        isError: true,
      }

      await this.context.addMessage(this.config.sessionId, {
        id: crypto.randomUUID(),
        role: 'tool',
        content: errorResult.output,
        toolResult: errorResult,
        createdAt: new Date(),
      })

      return errorResult
    }
  }

  private async emit(event: AgentEvent): Promise<void> {
    for (const handler of this.handlers) {
      try {
        await handler(event)
      } catch {
      }
    }
  }
}
