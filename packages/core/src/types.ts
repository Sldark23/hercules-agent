import { z } from 'zod'

// ─── Message & Session ──────────────────────────────────────────────

export type MessageRole = 'user' | 'assistant' | 'system' | 'tool'

export interface Message {
  id: string
  role: MessageRole
  content: string
  toolCalls?: ToolCall[]
  toolResult?: ToolResult
  metadata?: Record<string, unknown>
  createdAt: Date
}

export interface Session {
  id: string
  messages: Message[]
  metadata: SessionMetadata
  createdAt: Date
  updatedAt: Date
}

export interface SessionMetadata {
  userId?: string
  channelId?: string
  platform?: string
  modelId?: string
  title?: string
  tags?: string[]
}

// ─── Tools ──────────────────────────────────────────────────────────

export interface ToolDefinition {
  name: string
  description: string
  inputSchema: z.ZodSchema
  handler: (input: unknown, ctx: ToolContext) => Promise<ToolResult>
}

export interface ToolCall {
  id: string
  name: string
  arguments: Record<string, unknown>
}

export interface ToolResult {
  toolCallId: string
  output: string
  isError?: boolean
  metadata?: Record<string, unknown>
}

export interface ToolContext {
  sessionId: string
  userId?: string
  workspaceDir: string
  env: Record<string, string>
  abortSignal?: AbortSignal
}

// ─── Models / Providers ─────────────────────────────────────────────

export type ProviderId = 'anthropic' | 'openai' | 'google' | 'openrouter' | 'ollama' | 'mistral' | 'deepseek' | 'groq' | 'xai' | 'cohere' | 'together' | 'perplexity' | 'fireworks' | 'replicate' | 'huggingface' | 'anyscale' | 'azure' | 'github' | 'ai21' | 'octoai' | 'lepton' | 'deepinfra' | 'novita' | 'lambdatest' | string

export interface ModelConfig {
  id: string
  provider: ProviderId
  displayName: string
  contextWindow: number
  supportsVision: boolean
  supportsStreaming: boolean
  supportsThinking: boolean
  pricing: ModelPricing
  toolCallFormat?: 'native' | 'json' | 'custom'
}

export interface ModelPricing {
  inputPerMillion: number
  outputPerMillion: number
  cacheReadPerMillion?: number
  cacheWritePerMillion?: number
}

export interface ModelRequest {
  model: string
  messages: Array<{ role: MessageRole; content: string }>
  system?: string
  tools?: ToolDefinition[]
  maxTokens?: number
  temperature?: number
  streaming?: boolean
  thinking?: ThinkingLevel
  signal?: AbortSignal
}

export interface ModelResponse {
  id: string
  content: string
  toolCalls?: ToolCall[]
  usage: TokenUsage
  finishReason: 'stop' | 'tool_use' | 'max_tokens' | 'error'
  modelId: string
  thinking?: string
}

export interface TokenUsage {
  input: number
  output: number
  cacheRead?: number
  cacheWrite?: number
}

export type ThinkingLevel = 'off' | 'low' | 'medium' | 'high'

export interface ProviderConfig {
  id: ProviderId
  apiKey?: string
  baseUrl?: string
  models: ModelConfig[]
  defaultModel: string
  timeout?: number
  maxRetries?: number
}

// ─── Credentials ────────────────────────────────────────────────────

export interface Credential {
  id: string
  providerId: ProviderId
  apiKey: string
  baseUrl?: string
  isActive: boolean
  cooldownUntil?: Date
  failureCount: number
  metadata?: Record<string, unknown>
}

// ─── Context Engine ─────────────────────────────────────────────────

export interface ContextState {
  sessionId: string
  messages: Message[]
  tokenBudget: number
  usedTokens: number
  isCompressed: boolean
  compressionHistory: CompressionEvent[]
}

export interface CompressionEvent {
  timestamp: Date
  originalTokens: number
  compressedTokens: number
  summary: string
}

export interface ContextConfig {
  maxTokens: number
  compressionThreshold: number
  compressionTarget: number
  maxMessages: number
}

// ─── System Prompt ──────────────────────────────────────────────────

export interface SystemPromptConfig {
  persona: string
  skills?: SkillInjection[]
  memoryContext?: string
  toolInstructions?: string
  constraints?: string[]
  dynamicSections?: Array<{ name: string; content: string }>
}

export interface SkillInjection {
  name: string
  content: string
  priority: number
}

// ─── Agent Loop ─────────────────────────────────────────────────────

export type AgentState = 'idle' | 'thinking' | 'waiting_tool' | 'responding' | 'error' | 'done'

export interface AgentConfig {
  sessionId: string
  modelId: string
  systemPrompt: SystemPromptConfig
  tools: ToolDefinition[]
  contextConfig: ContextConfig
  maxTurns: number
  userId?: string
  workspaceDir: string
}

export interface AgentTurnResult {
  sessionId: string
  messages: Message[]
  usage: TokenUsage
  turns: number
  finishedReason: 'completed' | 'max_turns' | 'error' | 'cancelled'
  error?: string
}

// ─── Events ─────────────────────────────────────────────────────────

export type AgentEvent =
  | { type: 'thinking_start' }
  | { type: 'thinking_end'; thinking: string }
  | { type: 'tool_call'; toolCall: ToolCall }
  | { type: 'tool_result'; result: ToolResult }
  | { type: 'text_delta'; delta: string }
  | { type: 'text_done'; text: string }
  | { type: 'error'; error: string }
  | { type: 'state_change'; state: AgentState }
  | { type: 'done'; result: AgentTurnResult }

export type AgentEventHandler = (event: AgentEvent) => void | Promise<void>
