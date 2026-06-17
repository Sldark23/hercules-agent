import type { IncomingMessage, ServerResponse } from 'node:http'
import type { GatewayRoute } from './server.js'

export interface OpenAIChatMessage {
  role: 'system' | 'user' | 'assistant' | 'tool'
  content: string
  tool_calls?: Array<{
    id: string
    type: 'function'
    function: { name: string; arguments: string }
  }>
  tool_call_id?: string
  name?: string
}

export interface OpenAIChatRequest {
  model: string
  messages: OpenAIChatMessage[]
  max_tokens?: number
  temperature?: number
  stream?: boolean
  tools?: Array<{
    type: 'function'
    function: {
      name: string
      description: string
      parameters: Record<string, unknown>
    }
  }>
  tool_choice?: 'auto' | 'none' | 'required'
  user?: string
}

export interface ModelHandler {
  chatComplete(req: OpenAIChatRequest): Promise<OpenAIChatResponse>
  chatCompleteStream(req: OpenAIChatRequest): AsyncIterable<string>
}

export interface OpenAIChatResponse {
  id: string
  object: 'chat.completion'
  created: number
  model: string
  choices: Array<{
    index: number
    message: {
      role: 'assistant'
      content: string | null
      tool_calls?: Array<{
        id: string
        type: 'function'
        function: { name: string; arguments: string }
      }>
    }
    finish_reason: 'stop' | 'tool_calls' | 'length' | 'error'
  }>
  usage: {
    prompt_tokens: number
    completion_tokens: number
    total_tokens: number
  }
}

export function createOpenAICompatRoutes(handler: ModelHandler): GatewayRoute[] {
  return [
    {
      method: 'GET',
      path: '/v1/models',
      handler: (_req, res) => {
        res.writeHead(200, { 'Content-Type': 'application/json' })
        res.end(JSON.stringify({
          object: 'list',
          data: [
            { id: 'gpt-4', object: 'model', created: Date.now(), owned_by: 'hercules' },
            { id: 'gpt-4o', object: 'model', created: Date.now(), owned_by: 'hercules' },
            { id: 'claude-3-5-sonnet', object: 'model', created: Date.now(), owned_by: 'hercules' },
          ],
        }))
      },
    },
    {
      method: 'POST',
      path: '/v1/chat/completions',
      handler: async (_req, res, body) => {
        const req = body as OpenAIChatRequest
        if (!req) {
          res.writeHead(400, { 'Content-Type': 'application/json' })
          res.end(JSON.stringify({ error: 'Invalid request body' }))
          return
        }

        if (req.stream) {
          res.writeHead(200, {
            'Content-Type': 'text/event-stream',
            'Cache-Control': 'no-cache',
            Connection: 'keep-alive',
          })

          try {
            for await (const chunk of handler.chatCompleteStream(req)) {
              res.write(`data: ${chunk}\n\n`)
            }
            res.write('data: [DONE]\n\n')
            res.end()
          } catch (err) {
            res.write(`data: ${JSON.stringify({ error: (err as Error).message })}\n\n`)
            res.end()
          }
          return
        }

        try {
          const result = await handler.chatComplete(req)
          res.writeHead(200, { 'Content-Type': 'application/json' })
          res.end(JSON.stringify(result))
        } catch (err) {
          res.writeHead(500, { 'Content-Type': 'application/json' })
          res.end(JSON.stringify({ error: (err as Error).message }))
        }
      },
    },
    {
      method: 'POST',
      path: '/v1/embeddings',
      handler: async (_req, res) => {
        res.writeHead(200, { 'Content-Type': 'application/json' })
        res.end(JSON.stringify({
          object: 'list',
          data: [{ object: 'embedding', index: 0, embedding: [] }],
          model: 'text-embedding-ada-002',
          usage: { prompt_tokens: 0, total_tokens: 0 },
        }))
      },
    },
  ]
}

export function buildChatResponse(
  model: string,
  content: string,
  usage: { prompt: number; completion: number },
  finishReason: OpenAIChatResponse['choices'][0]['finish_reason'] = 'stop'
): OpenAIChatResponse {
  return {
    id: `chatcmpl-${Date.now()}`,
    object: 'chat.completion',
    created: Math.floor(Date.now() / 1000),
    model,
    choices: [{
      index: 0,
      message: { role: 'assistant', content },
      finish_reason: finishReason,
    }],
    usage: {
      prompt_tokens: usage.prompt,
      completion_tokens: usage.completion,
      total_tokens: usage.prompt + usage.completion,
    },
  }
}

export function buildStreamChunk(model: string, content: string, finishReason?: string): string {
  return JSON.stringify({
    id: `chatcmpl-${Date.now()}`,
    object: 'chat.completion.chunk',
    created: Math.floor(Date.now() / 1000),
    model,
    choices: [{
      index: 0,
      delta: { content },
      finish_reason: finishReason ?? null,
    }],
  })
}
