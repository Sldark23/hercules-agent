import type { ModelConfig, ModelRequest, ModelResponse, ProviderConfig, ProviderId, ThinkingLevel, TokenUsage, ToolCall } from './types.js'
import { CredentialPool } from './credential-pool.js'

export interface ModelRouterConfig {
  defaultProvider?: ProviderId
  defaultModel?: string
  fallbackChain: string[]
  maxRetries: number
  autoDiscover?: boolean
}

const PROVIDER_BASE_URLS: Record<string, string> = {
  anthropic: 'https://api.anthropic.com',
  openai: 'https://api.openai.com',
  google: 'https://generativelanguage.googleapis.com',
  mistral: 'https://api.mistral.ai',
  deepseek: 'https://api.deepseek.com',
  groq: 'https://api.groq.com',
  xai: 'https://api.x.ai',
  ollama_cloud: 'https://ollama.com',
  cohere: 'https://api.cohere.com',
  together: 'https://api.together.xyz',
  openrouter: 'https://openrouter.ai/api',
  perplexity: 'https://api.perplexity.ai',
  fireworks: 'https://api.fireworks.ai',
  replicate: 'https://api.replicate.com',
  huggingface: 'https://api-inference.huggingface.co',
  anyscale: 'https://api.endpoints.anyscale.com',
  github: 'https://models.inference.ai.azure.com',
  ai21: 'https://api.ai21.com',
  octoai: 'https://text.octoai.run',
  lepton: 'https://api.lepton.ai',
  deepinfra: 'https://api.deepinfra.com',
  novita: 'https://api.novita.ai',
  lambdatest: 'https://api.lambdatest.com',
  azure: 'https://YOUR_RESOURCE.openai.azure.com',
}

interface NamedAPI {
  baseUrl: string
  headers: Record<string, string>
  bodyTransform?: (body: Record<string, unknown>, model: ModelConfig, request: ModelRequest) => Record<string, unknown>
}

function getProviderApi(provider: string, credBaseUrl?: string): NamedAPI {
  const baseUrl = credBaseUrl ?? PROVIDER_BASE_URLS[provider] ?? 'https://api.openai.com'

  switch (provider) {
    case 'anthropic':
      return {
        baseUrl: `${baseUrl}/v1/messages`,
        headers: {
          'Content-Type': 'application/json',
          'x-api-key': '{{API_KEY}}',
          'anthropic-version': '2023-06-01',
        },
      }
    case 'google':
      return {
        baseUrl: `${baseUrl}/v1beta/models`,
        headers: { 'Content-Type': 'application/json' },
      }
    case 'ollama':
      return {
        baseUrl: 'http://localhost:11434/api/chat',
        headers: { 'Content-Type': 'application/json' },
      }
    case 'mistral':
      return {
        baseUrl: `${baseUrl}/v1/chat/completions`,
        headers: {
          'Content-Type': 'application/json',
          Authorization: 'Bearer {{API_KEY}}',
        },
      }
    case 'cohere':
      return {
        baseUrl: `${baseUrl}/v2/chat`,
        headers: {
          'Content-Type': 'application/json',
          Authorization: 'Bearer {{API_KEY}}',
        },
        bodyTransform: (body, _model, _request) => ({
          ...body,
          documents: body.documents ?? [],
        }),
      }
    case 'huggingface':
      return {
        baseUrl: `${baseUrl}/v1/chat/completions`,
        headers: {
          'Content-Type': 'application/json',
          Authorization: 'Bearer {{API_KEY}}',
        },
      }
    default:
      return {
        baseUrl: `${baseUrl}/v1/chat/completions`,
        headers: {
          'Content-Type': 'application/json',
          Authorization: 'Bearer {{API_KEY}}',
        },
      }
  }
}

interface ModelDiscoveryResult {
  providerId: string
  models: Array<{ id: string; displayName?: string }>
}

export class ModelRouter {
  private providers: Map<ProviderId, ProviderConfig> = new Map()
  private modelCache: Map<string, ModelConfig> = new Map()
  private credentialPool: CredentialPool
  private config: ModelRouterConfig
  private discoverCache: Map<string, ModelDiscoveryResult> = new Map()

  constructor(
    credentialPool: CredentialPool,
    config: Partial<ModelRouterConfig> = {}
  ) {
    this.credentialPool = credentialPool
    this.config = {
      fallbackChain: [],
      maxRetries: 2,
      autoDiscover: false,
      ...config,
    }
  }

  registerProvider(config: ProviderConfig): void {
    this.providers.set(config.id, config)
    for (const model of config.models) {
      this.modelCache.set(model.id, model)
    }
  }

  registerProviders(configs: ProviderConfig[]): void {
    for (const config of configs) this.registerProvider(config)
  }

  getModel(modelId: string): ModelConfig | undefined {
    return this.modelCache.get(modelId)
  }

  listModels(): ModelConfig[] {
    return Array.from(this.modelCache.values())
  }

  listProviders(): ProviderConfig[] {
    return Array.from(this.providers.values())
  }

  /**
   * Discover available models from a provider's API.
   * Uses the provider's models endpoint when available.
   */
  async discoverProviderModels(
    providerId: string,
    apiKey: string,
    baseUrl?: string
  ): Promise<ModelDiscoveryResult> {
    const cacheKey = `${providerId}:${apiKey.slice(0, 8)}`
    if (this.discoverCache.has(cacheKey)) return this.discoverCache.get(cacheKey)!

    let result: ModelDiscoveryResult = { providerId, models: [] }

    try {
      switch (providerId) {
        case 'anthropic': {
          const url = `${baseUrl ?? PROVIDER_BASE_URLS.anthropic}/v1/models`
          const res = await fetch(url, {
            headers: {
              'x-api-key': apiKey,
              'anthropic-version': '2023-06-01',
              'Content-Type': 'application/json',
            },
          })
          if (res.ok) {
            const data = (await res.json()) as Record<string, unknown>
            const models = (data.data as Array<Record<string, unknown>>) ?? []
            result.models = models
              .filter(m => (m.type as string) === 'model')
              .map(m => ({ id: m.id as string, displayName: m.display_name as string }))
          }
          break
        }
        case 'google': {
          const url = `${baseUrl ?? PROVIDER_BASE_URLS.google}/v1beta/models?key=${apiKey}`
          const res = await fetch(url)
          if (res.ok) {
            const data = (await res.json()) as Record<string, unknown>
            const models = (data.models as Array<Record<string, unknown>>) ?? []
            result.models = models
              .filter(m => (m.supportedGenerationMethods as string[] ?? []).includes('generateContent'))
              .map(m => ({
                id: (m.name as string).replace('models/', ''),
                displayName: m.displayName as string,
              }))
          }
          break
        }
        case 'ollama': {
          const res = await fetch('http://localhost:11434/api/tags')
          if (res.ok) {
            const data = (await res.json()) as Record<string, unknown>
            const models = (data.models as Array<Record<string, unknown>>) ?? []
            result.models = models.map(m => ({
              id: (m.name as string).replace(':latest', ''),
              displayName: m.name as string,
            }))
          }
          break
        }
        case 'openrouter': {
          const url = 'https://openrouter.ai/api/v1/models'
          const res = await fetch(url)
          if (res.ok) {
            const data = (await res.json()) as Record<string, unknown>
            const models = (data.data as Array<Record<string, unknown>>) ?? []
            result.models = models.map(m => ({
              id: m.id as string,
              displayName: (m.name as string) ?? (m.id as string),
            }))
          }
          break
        }
        default: {
          const url = `${baseUrl ?? PROVIDER_BASE_URLS[providerId] ?? 'https://api.openai.com'}/v1/models`
          const res = await fetch(url, {
            headers: {
              Authorization: `Bearer ${apiKey}`,
              'Content-Type': 'application/json',
            },
          })
          if (res.ok) {
            const data = (await res.json()) as Record<string, unknown>
            const models = (data.data as Array<Record<string, unknown>>) ?? []
            result.models = models.map(m => ({
              id: m.id as string,
              displayName: (m.id as string),
            }))
          }
          break
        }
      }
    } catch {
      // Discovery failed silently — presets will be used instead
    }

    this.discoverCache.set(cacheKey, result)
    return result
  }

  /**
   * Auto-register providers with their API keys, discovers models from each API,
   * and falls back to presets when discovery fails.
   */
  async autoConfigure(apiKeys: Record<string, string>): Promise<void> {
    const presets = createProviderPresets(apiKeys)
    const discoveryResults: Array<{ id: string; models: ProviderConfig }> = []

    for (const preset of presets) {
      const apiKey = apiKeys[preset.id]
      if (!apiKey && preset.id !== 'ollama') continue

      this.credentialPool.register({
        id: `${preset.id}-auto`,
        providerId: preset.id,
        apiKey: apiKey ?? '',
        isActive: true,
        failureCount: 0,
      })

      if (this.config.autoDiscover && apiKey) {
        const discovered = await this.discoverProviderModels(preset.id, apiKey, preset.baseUrl)
        if (discovered.models.length > 0) {
          const knownIds = new Set(preset.models.map(m => m.id))
          const newModels = discovered.models
            .filter(m => !knownIds.has(m.id))
            .map(m => ({
              id: m.id,
              provider: preset.id as ProviderId,
              displayName: m.displayName ?? m.id,
              contextWindow: 128000,
              supportsVision: m.id.includes('vision') || m.id.includes('vision'),
              supportsStreaming: true,
              supportsThinking: m.id.includes('reason') || m.id.includes('thinking'),
              pricing: { inputPerMillion: 0, outputPerMillion: 0 },
              toolCallFormat: 'native' as const,
            }))
          discoveryResults.push({
            id: preset.id,
            models: { ...preset, models: [...preset.models, ...newModels] },
          })
          continue
        }
      }

      discoveryResults.push({ id: preset.id, models: preset })
    }

    for (const result of discoveryResults) {
      this.registerProvider(result.models)
    }
  }

  async call(request: ModelRequest): Promise<ModelResponse> {
    const model = this.modelCache.get(request.model)
    if (!model) {
      const available = Array.from(this.modelCache.keys()).join(', ')
      throw new Error(`Model "${request.model}" not found. Available: ${available || 'none'}`)
    }

    const provider = this.providers.get(model.provider)
    if (!provider) throw new Error(`Provider "${model.provider}" not registered`)

    const cred = this.credentialPool.getActive(model.provider)
    if (!cred && !this.isLocalProvider(model.provider)) {
      throw new Error(`No active credential for provider "${model.provider}"`)
    }

    const errors: string[] = []

    const modelIdsToTry = [
      request.model,
      ...this.config.fallbackChain.filter(id => id !== request.model),
    ]

    for (const modelId of modelIdsToTry) {
      try {
        const response = await this.callModel(modelId, request, cred)
        if (cred) this.credentialPool.recordSuccess(cred.id)
        return response
      } catch (err) {
        if (cred) this.credentialPool.recordFailure(cred.id)
        errors.push(`${modelId}: ${(err as Error).message}`)
        if ((err as Error).message.includes('401') || (err as Error).message.includes('403')) break
      }
    }

    throw new Error(`All models failed: ${errors.join('; ')}`)
  }

  private async callModel(
    modelId: string,
    request: ModelRequest,
    cred?: { apiKey: string; baseUrl?: string }
  ): Promise<ModelResponse> {
    const model = this.modelCache.get(modelId)
    if (!model) throw new Error(`Model "${modelId}" not found`)

    switch (model.provider) {
      case 'anthropic':
        return this.callAnthropic(model, request, cred!)
      case 'openai':
      case 'groq':
      case 'xai':
      case 'deepseek':
      case 'mistral':
      case 'together':
      case 'openrouter':
      case 'perplexity':
      case 'fireworks':
      case 'replicate':
      case 'huggingface':
      case 'anyscale':
      case 'github':
      case 'ai21':
      case 'octoai':
      case 'lepton':
      case 'deepinfra':
      case 'novita':
      case 'lambdatest':
      case 'azure':
        return this.callOpenAICompatible(model, request, cred!)
      case 'google':
        return this.callGoogle(model, request, cred!)
      case 'cohere':
        return this.callCohere(model, request, cred!)
      case 'ollama':
        return this.callOllama(model, request, cred!)
      case 'ollama_cloud':
        return this.callOllama(model, request, cred!)
      default:
        return this.callOpenAICompatible(model, request, cred!)
    }
  }

  private buildRequestHeaders(
    provider: string,
    apiKey: string,
    extra?: Record<string, string>
  ): Record<string, string> {
    const api = getProviderApi(provider)
    const headers: Record<string, string> = {}
    for (const [key, value] of Object.entries(api.headers)) {
      headers[key] = value.replace('{{API_KEY}}', apiKey)
    }
    return { ...headers, ...extra }
  }

  private async callAnthropic(
    model: ModelConfig,
    request: ModelRequest,
    cred: { apiKey: string; baseUrl?: string }
  ): Promise<ModelResponse> {
    const url = `${cred.baseUrl ?? PROVIDER_BASE_URLS.anthropic}/v1/messages`
    const body: Record<string, unknown> = {
      model: model.id,
      max_tokens: request.maxTokens ?? 4096,
      messages: request.messages.map(m => ({ role: m.role, content: m.content })),
    }
    if (request.system) body.system = request.system
    if (request.tools?.length) {
      body.tools = request.tools.map(t => ({
        name: t.name,
        description: t.description,
        input_schema: t.inputSchema,
      }))
    }
    if (request.thinking && request.thinking !== 'off') {
      const budgetMapping: Record<string, number> = { low: 2048, medium: 4096, high: 8192 }
      body.thinking = { type: 'enabled', budget_tokens: budgetMapping[request.thinking] ?? 2048 }
    }

    const res = await fetch(url, {
      method: 'POST',
      headers: this.buildRequestHeaders('anthropic', cred.apiKey),
      body: JSON.stringify(body),
      signal: request.signal,
    })

    if (!res.ok) throw new Error(`Anthropic API error: ${res.status} ${await res.text()}`)
    const data = (await res.json()) as Record<string, unknown>

    return this.parseAnthropicResponse(data, model.id)
  }

  private parseAnthropicResponse(data: Record<string, unknown>, modelId: string): ModelResponse {
    const content = data.content as Array<Record<string, unknown>> | undefined
    const usage = data.usage as Record<string, unknown> | undefined

    let text = ''
    let thinking: string | undefined
    const toolCalls: Array<{ id: string; name: string; arguments: Record<string, unknown> }> = []

    if (content) {
      for (const block of content) {
        if (block.type === 'text') text += block.text
        if (block.type === 'thinking') thinking = (thinking ?? '') + (block.thinking as string ?? '')
        if (block.type === 'tool_use') {
          toolCalls.push({
            id: block.id as string,
            name: block.name as string,
            arguments: block.input as Record<string, unknown>,
          })
        }
      }
    }

    return {
      id: (data.id as string) ?? crypto.randomUUID(),
      content: text,
      toolCalls: toolCalls.length > 0 ? toolCalls : undefined,
      thinking,
      usage: {
        input: (usage?.input_tokens as number) ?? 0,
        output: (usage?.output_tokens as number) ?? 0,
      },
      finishReason: this.mapAnthropicStopReason(data.stop_reason as string),
      modelId,
    }
  }

  private mapAnthropicStopReason(reason?: string): ModelResponse['finishReason'] {
    switch (reason) {
      case 'end_turn': return 'stop'
      case 'tool_use': return 'tool_use'
      case 'max_tokens': return 'max_tokens'
      case 'error': return 'error'
      default: return 'stop'
    }
  }

  private async callGoogle(
    model: ModelConfig,
    request: ModelRequest,
    cred: { apiKey: string; baseUrl?: string }
  ): Promise<ModelResponse> {
    const url = `${cred.baseUrl ?? PROVIDER_BASE_URLS.google}/v1beta/models/${model.id}:generateContent`
    const body: Record<string, unknown> = {
      contents: request.messages.map(m => ({
        role: m.role === 'assistant' ? 'model' : m.role,
        parts: [{ text: m.content }],
      })),
      generationConfig: {
        maxOutputTokens: request.maxTokens ?? 4096,
        temperature: request.temperature ?? 0.7,
      },
    }

    if (request.system) {
      body.systemInstruction = { parts: [{ text: request.system }] }
    }

    const res = await fetch(`${url}?key=${cred.apiKey}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
      signal: request.signal,
    })

    if (!res.ok) throw new Error(`Google API error: ${res.status} ${await res.text()}`)
    const data = (await res.json()) as Record<string, unknown>
    const candidate = (data.candidates as Array<Record<string, unknown>>)?.[0]
    const content = candidate?.content as Record<string, unknown> | undefined
    const parts = content?.parts as Array<Record<string, unknown>> | undefined
    const text = parts?.map(p => p.text).filter(Boolean).join('') ?? ''
    const usage = data.usageMetadata as Record<string, unknown> | undefined

    return {
      id: crypto.randomUUID(),
      content: text,
      usage: {
        input: (usage?.promptTokenCount as number) ?? 0,
        output: (usage?.candidatesTokenCount as number) ?? 0,
      },
      finishReason: 'stop',
      modelId: model.id,
    }
  }

  private async callCohere(
    model: ModelConfig,
    request: ModelRequest,
    cred: { apiKey: string; baseUrl?: string }
  ): Promise<ModelResponse> {
    const baseUrl = cred.baseUrl ?? PROVIDER_BASE_URLS.cohere
    const body: Record<string, unknown> = {
      model: model.id,
      message: request.messages[request.messages.length - 1]?.content ?? '',
      chat_history: request.messages.slice(0, -1).map(m => ({
        role: m.role === 'assistant' ? 'CHATBOT' : 'USER',
        message: m.content,
      })),
      preamble: request.system ?? '',
      max_tokens: request.maxTokens ?? 4096,
      temperature: request.temperature ?? 0.7,
    }

    const res = await fetch(`${baseUrl}/v2/chat`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${cred.apiKey}`,
      },
      body: JSON.stringify(body),
      signal: request.signal,
    })

    if (!res.ok) throw new Error(`Cohere API error: ${res.status} ${await res.text()}`)
    const data = (await res.json()) as Record<string, unknown>

    const meta = data.meta as Record<string, unknown> | undefined
    const billed = meta?.billed_units as Record<string, unknown> | undefined

    return {
      id: (data.id as string) ?? crypto.randomUUID(),
      content: (data.text as string) ?? '',
      usage: {
        input: (billed?.input_tokens as number) ?? 0,
        output: (billed?.output_tokens as number) ?? 0,
      },
      finishReason: (data.finish_reason as ModelResponse['finishReason']) ?? 'stop',
      modelId: model.id,
    }
  }

  private async callOllama(
    model: ModelConfig,
    request: ModelRequest,
    cred?: { apiKey: string; baseUrl?: string }
  ): Promise<ModelResponse> {
    const baseUrl = cred?.baseUrl ?? PROVIDER_BASE_URLS[model.provider] ?? 'http://localhost:11434'
    const url = `${baseUrl}/api/chat`

    const body: Record<string, unknown> = {
      model: model.id,
      messages: [
        ...(request.system ? [{ role: 'system', content: request.system }] : []),
        ...request.messages,
      ],
      stream: request.streaming ?? false,
      options: {
        temperature: request.temperature ?? 0.7,
        num_predict: request.maxTokens ?? 4096,
      },
    }

    const headers: Record<string, string> = { 'Content-Type': 'application/json' }
    if (cred?.apiKey) headers['Authorization'] = `Bearer ${cred.apiKey}`

    const res = await fetch(url, {
      method: 'POST',
      headers,
      body: JSON.stringify(body),
      signal: request.signal,
    })

    if (!res.ok) throw new Error(`Ollama error: ${res.status} ${await res.text()}`)

    if (request.streaming && request.onDelta) {
      return this.handleOllamaStream(res, model.id, request.onDelta, request.signal)
    }

    const data = (await res.json()) as Record<string, unknown>

    return {
      id: crypto.randomUUID(),
      content: (data.message as Record<string, unknown>)?.content as string ?? '',
      usage: {
        input: (data.prompt_eval_count as number) ?? 0,
        output: (data.eval_count as number) ?? 0,
      },
      finishReason: data.done ? 'stop' : 'error',
      modelId: model.id,
    }
  }

  private async callOpenAICompatible(
    model: ModelConfig,
    request: ModelRequest,
    cred: { apiKey: string; baseUrl?: string }
  ): Promise<ModelResponse> {
    const actualBase = cred.baseUrl ?? PROVIDER_BASE_URLS[model.provider]
    const api = getProviderApi(model.provider)
    const url = `${actualBase ?? api.baseUrl}/v1/chat/completions`
    const body = this.buildOpenAIBody(model, request)
    const headers = this.buildRequestHeaders(model.provider, cred.apiKey)

    const res = await fetch(url, {
      method: 'POST',
      headers,
      body: JSON.stringify(body),
      signal: request.signal,
    })

    if (!res.ok) throw new Error(`${model.provider} API error: ${res.status} ${await res.text()}`)

    if (request.streaming && request.onDelta) {
      return this.handleOpenAIStream(res, model.id, request.onDelta, request.signal)
    }

    const data = (await res.json()) as Record<string, unknown>
    return this.parseOpenAIResponse(data, model.id)
  }

  private async handleOpenAIStream(
    res: Response,
    modelId: string,
    onDelta: (delta: string) => void,
    signal?: AbortSignal
  ): Promise<ModelResponse> {
    const reader = res.body?.getReader()
    if (!reader) throw new Error('Response body not readable')

    const decoder = new TextDecoder()
    let buffer = ''
    let content = ''
    let finishReason: ModelResponse['finishReason'] = 'stop'
    let responseId = crypto.randomUUID() as string
    let toolCalls: ToolCall[] | undefined

    try {
      while (true) {
        const { done, value } = await reader.read()
        if (done || signal?.aborted) break

        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop() ?? ''

        for (const line of lines) {
          const trimmed = line.trim()
          if (!trimmed || !trimmed.startsWith('data: ')) continue
          const payload = trimmed.slice(6)
          if (payload === '[DONE]') break

          try {
            const chunk = JSON.parse(payload) as Record<string, unknown>
            if (chunk.id) responseId = chunk.id as string

            const choices = chunk.choices as Array<Record<string, unknown>> | undefined
            if (!choices?.length) continue

            const choice = choices[0]!
            if (choice.finish_reason) {
              finishReason = choice.finish_reason as ModelResponse['finishReason']
            }

            const delta = choice.delta as Record<string, unknown> | undefined
            if (!delta) continue

            if (typeof delta.content === 'string') {
              onDelta(delta.content)
              content += delta.content
            }

            const tcData = delta.tool_calls as Array<Record<string, unknown>> | undefined
            if (tcData?.length) {
              toolCalls = tcData.map(tc => ({
                id: tc.id as string,
                name: (tc.function as Record<string, unknown>)?.name as string ?? '',
                arguments: (() => {
                  try { return JSON.parse((tc.function as Record<string, unknown>)?.arguments as string) as Record<string, unknown> }
                  catch { return {} }
                })(),
              }))
            }
          } catch {}
        }
      }
    } finally {
      reader.releaseLock()
    }

    return {
      id: responseId,
      content,
      toolCalls,
      usage: { input: 0, output: 0 },
      finishReason,
      modelId,
    }
  }

  private async handleOllamaStream(
    res: Response,
    modelId: string,
    onDelta: (delta: string) => void,
    signal?: AbortSignal
  ): Promise<ModelResponse> {
    const reader = res.body?.getReader()
    if (!reader) throw new Error('Response body not readable')

    const decoder = new TextDecoder()
    let buffer = ''
    let content = ''
    let inputTokens = 0
    let outputTokens = 0

    try {
      while (true) {
        const { done, value } = await reader.read()
        if (done || signal?.aborted) break

        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop() ?? ''

        for (const line of lines) {
          const trimmed = line.trim()
          if (!trimmed) continue

          try {
            const chunk = JSON.parse(trimmed) as Record<string, unknown>
            const msg = chunk.message as Record<string, unknown> | undefined
            if (msg?.content) {
              const delta = msg.content as string
              onDelta(delta)
              content += delta
            }
            if (chunk.prompt_eval_count) inputTokens = chunk.prompt_eval_count as number
            if (chunk.eval_count) outputTokens = chunk.eval_count as number
          } catch {}
        }
      }
    } finally {
      reader.releaseLock()
    }

    return {
      id: crypto.randomUUID(),
      content,
      usage: { input: inputTokens, output: outputTokens },
      finishReason: 'stop',
      modelId,
    }
  }

  private buildOpenAIBody(model: ModelConfig, request: ModelRequest): Record<string, unknown> {
    const body: Record<string, unknown> = {
      model: model.id,
      messages: [
        ...(request.system ? [{ role: 'system', content: request.system }] : []),
        ...request.messages,
      ],
      max_tokens: request.maxTokens ?? 4096,
      stream: request.streaming ?? false,
      temperature: request.temperature ?? 0.7,
    }

    if (request.tools?.length) {
      body.tools = request.tools.map(t => ({
        type: 'function',
        function: {
          name: t.name,
          description: t.description,
          parameters: t.inputSchema,
        },
      }))
    }

    return body
  }

  private parseOpenAIResponse(data: Record<string, unknown>, modelId: string): ModelResponse {
    const choice = (data.choices as Array<Record<string, unknown>>)?.[0]
    const message = choice?.message as Record<string, unknown> | undefined
    const usage = data.usage as Record<string, unknown> | undefined
    const toolCallsData = message?.tool_calls as Array<Record<string, unknown>> | undefined

    const toolCalls = toolCallsData?.map(tc => ({
      id: tc.id as string,
      name: (tc.function as Record<string, unknown>)?.name as string,
      arguments: JSON.parse((tc.function as Record<string, unknown>)?.arguments as string) as Record<string, unknown>,
    }))

    return {
      id: data.id as string ?? crypto.randomUUID(),
      content: (message?.content as string) ?? '',
      toolCalls: toolCalls?.length ? toolCalls : undefined,
      usage: {
        input: (usage?.prompt_tokens as number) ?? 0,
        output: (usage?.completion_tokens as number) ?? 0,
        cacheRead: (usage?.cache_read_input_tokens as number) ?? undefined,
        cacheWrite: (usage?.cache_creation_input_tokens as number) ?? undefined,
      },
      finishReason: (choice?.finish_reason as ModelResponse['finishReason']) ?? 'stop',
      modelId,
    }
  }

  private isLocalProvider(providerId: string): boolean {
    return providerId === 'ollama' || providerId === 'local'
  }
}

export function createProviderPresets(apiKeys?: Partial<Record<string, string>>): ProviderConfig[] {
  return [
    {
      id: 'anthropic',
      baseUrl: PROVIDER_BASE_URLS.anthropic,
      defaultModel: 'claude-sonnet-4-20250514',
      models: [
        { id: 'claude-sonnet-4-20250514', provider: 'anthropic', displayName: 'Claude Sonnet 4', contextWindow: 200000, supportsVision: true, supportsStreaming: true, supportsThinking: true, pricing: { inputPerMillion: 3, outputPerMillion: 15 }, toolCallFormat: 'native' },
        { id: 'claude-haiku-3-5-20241022', provider: 'anthropic', displayName: 'Claude Haiku 3.5', contextWindow: 200000, supportsVision: true, supportsStreaming: true, supportsThinking: false, pricing: { inputPerMillion: 0.8, outputPerMillion: 4 }, toolCallFormat: 'native' },
        { id: 'claude-opus-4-20250514', provider: 'anthropic', displayName: 'Claude Opus 4', contextWindow: 200000, supportsVision: true, supportsStreaming: true, supportsThinking: true, pricing: { inputPerMillion: 15, outputPerMillion: 75 }, toolCallFormat: 'native' },
      ],
    },
    {
      id: 'openai',
      baseUrl: PROVIDER_BASE_URLS.openai,
      defaultModel: 'gpt-4o',
      models: [
        { id: 'gpt-4o', provider: 'openai', displayName: 'GPT-4o', contextWindow: 128000, supportsVision: true, supportsStreaming: true, supportsThinking: false, pricing: { inputPerMillion: 2.5, outputPerMillion: 10 }, toolCallFormat: 'native' },
        { id: 'gpt-4o-mini', provider: 'openai', displayName: 'GPT-4o Mini', contextWindow: 128000, supportsVision: true, supportsStreaming: true, supportsThinking: false, pricing: { inputPerMillion: 0.15, outputPerMillion: 0.6 }, toolCallFormat: 'native' },
        { id: 'o3-mini', provider: 'openai', displayName: 'o3 Mini', contextWindow: 200000, supportsVision: false, supportsStreaming: true, supportsThinking: true, pricing: { inputPerMillion: 1.1, outputPerMillion: 4.4 }, toolCallFormat: 'native' },
        { id: 'o4-mini', provider: 'openai', displayName: 'o4 Mini', contextWindow: 200000, supportsVision: true, supportsStreaming: true, supportsThinking: true, pricing: { inputPerMillion: 1.1, outputPerMillion: 4.4 }, toolCallFormat: 'native' },
        { id: 'gpt-4.1', provider: 'openai', displayName: 'GPT-4.1', contextWindow: 1000000, supportsVision: true, supportsStreaming: true, supportsThinking: false, pricing: { inputPerMillion: 2, outputPerMillion: 8 }, toolCallFormat: 'native' },
        { id: 'gpt-4.1-mini', provider: 'openai', displayName: 'GPT-4.1 Mini', contextWindow: 1000000, supportsVision: true, supportsStreaming: true, supportsThinking: false, pricing: { inputPerMillion: 0.4, outputPerMillion: 1.6 }, toolCallFormat: 'native' },
      ],
    },
    {
      id: 'google',
      baseUrl: PROVIDER_BASE_URLS.google,
      defaultModel: 'gemini-2.5-flash',
      models: [
        { id: 'gemini-2.5-flash', provider: 'google', displayName: 'Gemini 2.5 Flash', contextWindow: 1000000, supportsVision: true, supportsStreaming: true, supportsThinking: true, pricing: { inputPerMillion: 0.15, outputPerMillion: 0.6 }, toolCallFormat: 'native' },
        { id: 'gemini-2.5-pro', provider: 'google', displayName: 'Gemini 2.5 Pro', contextWindow: 1000000, supportsVision: true, supportsStreaming: true, supportsThinking: true, pricing: { inputPerMillion: 1.25, outputPerMillion: 5 }, toolCallFormat: 'native' },
      ],
    },
    {
      id: 'mistral',
      baseUrl: PROVIDER_BASE_URLS.mistral,
      defaultModel: 'mistral-large-2503',
      models: [
        { id: 'mistral-large-2503', provider: 'mistral', displayName: 'Mistral Large', contextWindow: 128000, supportsVision: true, supportsStreaming: true, supportsThinking: false, pricing: { inputPerMillion: 2, outputPerMillion: 6 }, toolCallFormat: 'native' },
        { id: 'mistral-small-2503', provider: 'mistral', displayName: 'Mistral Small', contextWindow: 128000, supportsVision: true, supportsStreaming: true, supportsThinking: false, pricing: { inputPerMillion: 0.2, outputPerMillion: 0.6 }, toolCallFormat: 'native' },
        { id: 'codestral-2503', provider: 'mistral', displayName: 'Codestral', contextWindow: 256000, supportsVision: false, supportsStreaming: true, supportsThinking: false, pricing: { inputPerMillion: 1, outputPerMillion: 3 }, toolCallFormat: 'native' },
      ],
    },
    {
      id: 'deepseek',
      baseUrl: PROVIDER_BASE_URLS.deepseek,
      defaultModel: 'deepseek-chat',
      models: [
        { id: 'deepseek-chat', provider: 'deepseek', displayName: 'DeepSeek V3', contextWindow: 64000, supportsVision: false, supportsStreaming: true, supportsThinking: false, pricing: { inputPerMillion: 0.27, outputPerMillion: 1.1 }, toolCallFormat: 'native' },
        { id: 'deepseek-reasoner', provider: 'deepseek', displayName: 'DeepSeek R1', contextWindow: 64000, supportsVision: false, supportsStreaming: true, supportsThinking: true, pricing: { inputPerMillion: 0.55, outputPerMillion: 2.19 }, toolCallFormat: 'native' },
      ],
    },
    {
      id: 'groq',
      baseUrl: PROVIDER_BASE_URLS.groq,
      defaultModel: 'llama-4-scout-17b-16e-instruct',
      models: [
        { id: 'llama-4-scout-17b-16e-instruct', provider: 'groq', displayName: 'Llama 4 Scout', contextWindow: 1000000, supportsVision: true, supportsStreaming: true, supportsThinking: false, pricing: { inputPerMillion: 0, outputPerMillion: 0 }, toolCallFormat: 'native' },
        { id: 'llama-4-maverick-17b-128e-instruct', provider: 'groq', displayName: 'Llama 4 Maverick', contextWindow: 1000000, supportsVision: true, supportsStreaming: true, supportsThinking: false, pricing: { inputPerMillion: 0, outputPerMillion: 0 }, toolCallFormat: 'native' },
        { id: 'mixtral-8x7b-32768', provider: 'groq', displayName: 'Mixtral 8x7B', contextWindow: 32768, supportsVision: false, supportsStreaming: true, supportsThinking: false, pricing: { inputPerMillion: 0, outputPerMillion: 0 }, toolCallFormat: 'native' },
        { id: 'deepseek-r1-distill-llama-70b', provider: 'groq', displayName: 'DeepSeek R1 70B', contextWindow: 128000, supportsVision: false, supportsStreaming: true, supportsThinking: true, pricing: { inputPerMillion: 0, outputPerMillion: 0 }, toolCallFormat: 'native' },
      ],
    },
    {
      id: 'xai',
      baseUrl: PROVIDER_BASE_URLS.xai,
      defaultModel: 'grok-3',
      models: [
        { id: 'grok-3', provider: 'xai', displayName: 'Grok 3', contextWindow: 131072, supportsVision: true, supportsStreaming: true, supportsThinking: false, pricing: { inputPerMillion: 3, outputPerMillion: 15 }, toolCallFormat: 'native' },
        { id: 'grok-3-mini', provider: 'xai', displayName: 'Grok 3 Mini', contextWindow: 131072, supportsVision: false, supportsStreaming: true, supportsThinking: false, pricing: { inputPerMillion: 0.3, outputPerMillion: 1.5 }, toolCallFormat: 'native' },
      ],
    },
    {
      id: 'cohere',
      baseUrl: PROVIDER_BASE_URLS.cohere,
      defaultModel: 'command-a-03-2025',
      models: [
        { id: 'command-a-03-2025', provider: 'cohere', displayName: 'Command A', contextWindow: 256000, supportsVision: false, supportsStreaming: true, supportsThinking: false, pricing: { inputPerMillion: 2.5, outputPerMillion: 10 }, toolCallFormat: 'native' },
      ],
    },
    {
      id: 'together',
      baseUrl: PROVIDER_BASE_URLS.together,
      defaultModel: 'meta-llama/Llama-4-Scout-17B-16E-Instruct',
      models: [
        { id: 'meta-llama/Llama-4-Scout-17B-16E-Instruct', provider: 'together', displayName: 'Llama 4 Scout', contextWindow: 1000000, supportsVision: true, supportsStreaming: true, supportsThinking: false, pricing: { inputPerMillion: 0.1, outputPerMillion: 0.1 }, toolCallFormat: 'native' },
      ],
    },
    {
      id: 'perplexity',
      baseUrl: PROVIDER_BASE_URLS.perplexity,
      defaultModel: 'sonar-pro',
      models: [
        { id: 'sonar-pro', provider: 'perplexity', displayName: 'Sonar Pro', contextWindow: 200000, supportsVision: false, supportsStreaming: true, supportsThinking: false, pricing: { inputPerMillion: 3, outputPerMillion: 15 }, toolCallFormat: 'native' },
        { id: 'sonar', provider: 'perplexity', displayName: 'Sonar', contextWindow: 127000, supportsVision: false, supportsStreaming: true, supportsThinking: false, pricing: { inputPerMillion: 1, outputPerMillion: 5 }, toolCallFormat: 'native' },
      ],
    },
    {
      id: 'fireworks',
      baseUrl: PROVIDER_BASE_URLS.fireworks,
      defaultModel: 'accounts/fireworks/models/llama-v4-scout-17b-16e-instruct',
      models: [
        { id: 'accounts/fireworks/models/llama-v4-scout-17b-16e-instruct', provider: 'fireworks', displayName: 'Llama 4 Scout', contextWindow: 1000000, supportsVision: true, supportsStreaming: true, supportsThinking: false, pricing: { inputPerMillion: 0.07, outputPerMillion: 0.07 }, toolCallFormat: 'native' },
        { id: 'accounts/fireworks/models/deepseek-r1', provider: 'fireworks', displayName: 'DeepSeek R1', contextWindow: 128000, supportsVision: false, supportsStreaming: true, supportsThinking: true, pricing: { inputPerMillion: 0.5, outputPerMillion: 2 }, toolCallFormat: 'native' },
      ],
    },
    {
      id: 'replicate',
      baseUrl: PROVIDER_BASE_URLS.replicate,
      defaultModel: 'meta/meta-llama-3-70b-instruct',
      models: [
        { id: 'meta/meta-llama-3-70b-instruct', provider: 'replicate', displayName: 'Llama 3 70B', contextWindow: 8192, supportsVision: false, supportsStreaming: true, supportsThinking: false, pricing: { inputPerMillion: 0.65, outputPerMillion: 2.75 }, toolCallFormat: 'native' },
      ],
    },
    {
      id: 'huggingface',
      baseUrl: PROVIDER_BASE_URLS.huggingface,
      defaultModel: 'meta-llama/Llama-3.3-70B-Instruct',
      models: [
        { id: 'meta-llama/Llama-3.3-70B-Instruct', provider: 'huggingface', displayName: 'Llama 3.3 70B', contextWindow: 8192, supportsVision: false, supportsStreaming: true, supportsThinking: false, pricing: { inputPerMillion: 0, outputPerMillion: 0 }, toolCallFormat: 'native' },
      ],
    },
    {
      id: 'anyscale',
      baseUrl: PROVIDER_BASE_URLS.anyscale,
      defaultModel: 'meta-llama/Llama-3.3-70B-Instruct',
      models: [
        { id: 'meta-llama/Llama-3.3-70B-Instruct', provider: 'anyscale', displayName: 'Llama 3.3 70B', contextWindow: 128000, supportsVision: false, supportsStreaming: true, supportsThinking: false, pricing: { inputPerMillion: 0.45, outputPerMillion: 0.45 }, toolCallFormat: 'native' },
      ],
    },
    {
      id: 'github',
      baseUrl: PROVIDER_BASE_URLS.github,
      defaultModel: 'gpt-4o',
      models: [
        { id: 'gpt-4o', provider: 'github', displayName: 'GPT-4o (GitHub)', contextWindow: 128000, supportsVision: true, supportsStreaming: true, supportsThinking: false, pricing: { inputPerMillion: 0, outputPerMillion: 0 }, toolCallFormat: 'native' },
        { id: 'gpt-4o-mini', provider: 'github', displayName: 'GPT-4o Mini (GitHub)', contextWindow: 128000, supportsVision: true, supportsStreaming: true, supportsThinking: false, pricing: { inputPerMillion: 0, outputPerMillion: 0 }, toolCallFormat: 'native' },
        { id: 'o3-mini', provider: 'github', displayName: 'o3 Mini (GitHub)', contextWindow: 200000, supportsVision: false, supportsStreaming: true, supportsThinking: true, pricing: { inputPerMillion: 0, outputPerMillion: 0 }, toolCallFormat: 'native' },
      ],
    },
    {
      id: 'ai21',
      baseUrl: PROVIDER_BASE_URLS.ai21,
      defaultModel: 'jamba-1.6-mini',
      models: [
        { id: 'jamba-1.6-mini', provider: 'ai21', displayName: 'Jamba 1.6 Mini', contextWindow: 256000, supportsVision: false, supportsStreaming: true, supportsThinking: false, pricing: { inputPerMillion: 0.2, outputPerMillion: 0.4 }, toolCallFormat: 'native' },
        { id: 'jamba-1.6-large', provider: 'ai21', displayName: 'Jamba 1.6 Large', contextWindow: 256000, supportsVision: false, supportsStreaming: true, supportsThinking: false, pricing: { inputPerMillion: 2, outputPerMillion: 8 }, toolCallFormat: 'native' },
      ],
    },
    {
      id: 'octoai',
      baseUrl: PROVIDER_BASE_URLS.octoai,
      defaultModel: 'meta-llama-3.1-70b-instruct',
      models: [
        { id: 'meta-llama-3.1-70b-instruct', provider: 'octoai', displayName: 'Llama 3.1 70B', contextWindow: 128000, supportsVision: false, supportsStreaming: true, supportsThinking: false, pricing: { inputPerMillion: 0.18, outputPerMillion: 0.18 }, toolCallFormat: 'native' },
      ],
    },
    {
      id: 'lepton',
      baseUrl: PROVIDER_BASE_URLS.lepton,
      defaultModel: 'llama3-70b',
      models: [
        { id: 'llama3-70b', provider: 'lepton', displayName: 'Llama 3 70B', contextWindow: 8192, supportsVision: false, supportsStreaming: true, supportsThinking: false, pricing: { inputPerMillion: 0.21, outputPerMillion: 0.21 }, toolCallFormat: 'native' },
      ],
    },
    {
      id: 'deepinfra',
      baseUrl: PROVIDER_BASE_URLS.deepinfra,
      defaultModel: 'meta-llama/Llama-3.3-70B-Instruct',
      models: [
        { id: 'meta-llama/Llama-3.3-70B-Instruct', provider: 'deepinfra', displayName: 'Llama 3.3 70B', contextWindow: 128000, supportsVision: false, supportsStreaming: true, supportsThinking: false, pricing: { inputPerMillion: 0.23, outputPerMillion: 0.23 }, toolCallFormat: 'native' },
        { id: 'deepseek-r1', provider: 'deepinfra', displayName: 'DeepSeek R1', contextWindow: 128000, supportsVision: false, supportsStreaming: true, supportsThinking: true, pricing: { inputPerMillion: 1.3, outputPerMillion: 5.2 }, toolCallFormat: 'native' },
      ],
    },
    {
      id: 'novita',
      baseUrl: PROVIDER_BASE_URLS.novita,
      defaultModel: 'meta-llama/llama-4-scout-17b-16e-instruct',
      models: [
        { id: 'meta-llama/llama-4-scout-17b-16e-instruct', provider: 'novita', displayName: 'Llama 4 Scout', contextWindow: 1000000, supportsVision: true, supportsStreaming: true, supportsThinking: false, pricing: { inputPerMillion: 0.09, outputPerMillion: 0.09 }, toolCallFormat: 'native' },
      ],
    },
    {
      id: 'lambdatest',
      baseUrl: PROVIDER_BASE_URLS.lambdatest,
      defaultModel: 'llama-4-scout-17b-16e-instruct',
      models: [
        { id: 'llama-4-scout-17b-16e-instruct', provider: 'lambdatest', displayName: 'Llama 4 Scout', contextWindow: 1000000, supportsVision: true, supportsStreaming: true, supportsThinking: false, pricing: { inputPerMillion: 0.07, outputPerMillion: 0.07 }, toolCallFormat: 'native' },
      ],
    },
    {
      id: 'openrouter',
      baseUrl: PROVIDER_BASE_URLS.openrouter,
      defaultModel: 'anthropic/claude-sonnet-4',
      models: [
        { id: 'anthropic/claude-sonnet-4', provider: 'openrouter', displayName: 'Claude Sonnet 4 (OpenRouter)', contextWindow: 200000, supportsVision: true, supportsStreaming: true, supportsThinking: true, pricing: { inputPerMillion: 3, outputPerMillion: 15 }, toolCallFormat: 'native' },
        { id: 'openai/gpt-4o', provider: 'openrouter', displayName: 'GPT-4o (OpenRouter)', contextWindow: 128000, supportsVision: true, supportsStreaming: true, supportsThinking: false, pricing: { inputPerMillion: 2.5, outputPerMillion: 10 }, toolCallFormat: 'native' },
      ],
    },
    {
      id: 'ollama',
      baseUrl: 'http://localhost:11434',
      defaultModel: 'llama3.2',
      models: [
        { id: 'llama3.2', provider: 'ollama', displayName: 'Llama 3.2', contextWindow: 8192, supportsVision: false, supportsStreaming: true, supportsThinking: false, pricing: { inputPerMillion: 0, outputPerMillion: 0 }, toolCallFormat: 'native' },
        { id: 'llama3.1', provider: 'ollama', displayName: 'Llama 3.1', contextWindow: 8192, supportsVision: false, supportsStreaming: true, supportsThinking: false, pricing: { inputPerMillion: 0, outputPerMillion: 0 }, toolCallFormat: 'native' },
        { id: 'mistral', provider: 'ollama', displayName: 'Mistral', contextWindow: 8192, supportsVision: false, supportsStreaming: true, supportsThinking: false, pricing: { inputPerMillion: 0, outputPerMillion: 0 }, toolCallFormat: 'native' },
        { id: 'qwen2.5', provider: 'ollama', displayName: 'Qwen 2.5', contextWindow: 32768, supportsVision: false, supportsStreaming: true, supportsThinking: false, pricing: { inputPerMillion: 0, outputPerMillion: 0 }, toolCallFormat: 'native' },
      ],
    },
    {
      id: 'ollama_cloud',
      baseUrl: PROVIDER_BASE_URLS.ollama_cloud,
      defaultModel: 'llama3.2',
      models: [
        { id: 'llama3.2', provider: 'ollama_cloud', displayName: 'Llama 3.2', contextWindow: 8192, supportsVision: false, supportsStreaming: true, supportsThinking: false, pricing: { inputPerMillion: 0, outputPerMillion: 0 }, toolCallFormat: 'native' },
        { id: 'llama3.1', provider: 'ollama_cloud', displayName: 'Llama 3.1', contextWindow: 8192, supportsVision: false, supportsStreaming: true, supportsThinking: false, pricing: { inputPerMillion: 0, outputPerMillion: 0 }, toolCallFormat: 'native' },
        { id: 'mistral', provider: 'ollama_cloud', displayName: 'Mistral', contextWindow: 8192, supportsVision: false, supportsStreaming: true, supportsThinking: false, pricing: { inputPerMillion: 0, outputPerMillion: 0 }, toolCallFormat: 'native' },
        { id: 'qwen2.5', provider: 'ollama_cloud', displayName: 'Qwen 2.5', contextWindow: 32768, supportsVision: false, supportsStreaming: true, supportsThinking: false, pricing: { inputPerMillion: 0, outputPerMillion: 0 }, toolCallFormat: 'native' },
      ],
    },
  ]
}
