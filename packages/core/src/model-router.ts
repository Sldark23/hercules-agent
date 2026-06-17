import type { ModelConfig, ModelRequest, ModelResponse, ProviderConfig, ProviderId, ThinkingLevel, TokenUsage } from './types.js'
import { CredentialPool } from './credential-pool.js'

export interface ModelRouterConfig {
  defaultProvider?: ProviderId
  defaultModel?: string
  fallbackChain: string[]
  maxRetries: number
}

const PROVIDER_BASE_URLS: Record<string, string> = {
  anthropic: 'https://api.anthropic.com',
  openai: 'https://api.openai.com',
  google: 'https://generativelanguage.googleapis.com',
  mistral: 'https://api.mistral.ai',
  deepseek: 'https://api.deepseek.com',
  groq: 'https://api.groq.com',
  xai: 'https://api.x.ai',
  cohere: 'https://api.cohere.com',
  together: 'https://api.together.xyz',
  openrouter: 'https://openrouter.ai/api',
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

export class ModelRouter {
  private providers: Map<ProviderId, ProviderConfig> = new Map()
  private modelCache: Map<string, ModelConfig> = new Map()
  private credentialPool: CredentialPool
  private config: ModelRouterConfig

  constructor(
    credentialPool: CredentialPool,
    config: Partial<ModelRouterConfig> = {}
  ) {
    this.credentialPool = credentialPool
    this.config = {
      fallbackChain: [],
      maxRetries: 2,
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

  useProviderDefaults(apiKeys?: Partial<Record<string, string>>): void {
    const presets = createProviderPresets(apiKeys)
    for (const preset of presets) {
      if (this.credentialPool.hasAvailable(preset.id)) continue
      if (apiKeys?.[preset.id]) {
        this.credentialPool.register({
          id: `${preset.id}-default`,
          providerId: preset.id,
          apiKey: apiKeys[preset.id]!,
          isActive: true,
        })
      }
      this.registerProvider(preset)
    }
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
        return this.callOpenAICompatible(model, request, cred!)
      case 'google':
        return this.callGoogle(model, request, cred!)
      case 'cohere':
        return this.callCohere(model, request, cred!)
      case 'ollama':
        return this.callOllama(model, request)
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

  private async callMistral(
    model: ModelConfig,
    request: ModelRequest,
    cred: { apiKey: string; baseUrl?: string }
  ): Promise<ModelResponse> {
    const baseUrl = cred.baseUrl ?? PROVIDER_BASE_URLS.mistral
    const body: Record<string, unknown> = {
      model: model.id,
      messages: [
        ...(request.system ? [{ role: 'system', content: request.system }] : []),
        ...request.messages,
      ],
      max_tokens: request.maxTokens ?? 4096,
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

    const res = await fetch(`${baseUrl}/v1/chat/completions`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${cred.apiKey}`,
      },
      body: JSON.stringify(body),
      signal: request.signal,
    })

    if (!res.ok) throw new Error(`Mistral API error: ${res.status} ${await res.text()}`)
    const data = (await res.json()) as Record<string, unknown>
    return this.parseOpenAIResponse(data, model.id)
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

    return {
      id: data.id as string ?? crypto.randomUUID(),
      content: (data.text as string) ?? (data.message?.content?.[0]?.text as string) ?? '',
      usage: {
        input: (data.meta?.billed_units?.input_tokens as number) ?? 0,
        output: (data.meta?.billed_units?.output_tokens as number) ?? 0,
      },
      finishReason: (data.finish_reason as ModelResponse['finishReason']) ?? 'stop',
      modelId: model.id,
    }
  }

  private async callOllama(
    model: ModelConfig,
    request: ModelRequest
  ): Promise<ModelResponse> {
    const body: Record<string, unknown> = {
      model: model.id,
      messages: [
        ...(request.system ? [{ role: 'system', content: request.system }] : []),
        ...request.messages,
      ],
      stream: false,
      options: {
        temperature: request.temperature ?? 0.7,
        num_predict: request.maxTokens ?? 4096,
      },
    }

    const res = await fetch('http://localhost:11434/api/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
      signal: request.signal,
    })

    if (!res.ok) throw new Error(`Ollama error: ${res.status} ${await res.text()}`)
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
    const api = getProviderApi(model.provider)
    const url = `${cred.baseUrl ?? PROVIDER_BASE_URLS[model.provider] ?? api.baseUrl}/v1/chat/completions`
    const body = this.buildOpenAIBody(model, request)
    const headers = this.buildRequestHeaders(model.provider, cred.apiKey)

    const res = await fetch(url, {
      method: 'POST',
      headers,
      body: JSON.stringify(body),
      signal: request.signal,
    })

    if (!res.ok) throw new Error(`${model.provider} API error: ${res.status} ${await res.text()}`)
    const data = (await res.json()) as Record<string, unknown>
    return this.parseOpenAIResponse(data, model.id)
  }

  private buildOpenAIBody(model: ModelConfig, request: ModelRequest): Record<string, unknown> {
    const body: Record<string, unknown> = {
      model: model.id,
      messages: [
        ...(request.system ? [{ role: 'system', content: request.system }] : []),
        ...request.messages,
      ],
      max_tokens: request.maxTokens ?? 4096,
      stream: false,
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
  ]
}
