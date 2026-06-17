import type { AgentConfig, AgentTurnResult, ToolDefinition } from '@hercules/core'

// ─── Agent Profile ──────────────────────────────────────────────

export type AgentCapability =
  | 'code'
  | 'research'
  | 'writing'
  | 'analysis'
  | 'planning'
  | 'debugging'
  | 'review'
  | 'data'
  | 'creative'
  | 'support'
  | string

export interface AgentProfile {
  id: string
  name: string
  role: string
  description: string
  capabilities: AgentCapability[]
  modelId: string
  systemPrompt: string
  tools: ToolDefinition[]
  maxTurns: number
  temperature?: number
  weight?: number
}

export type AgentState = 'idle' | 'busy' | 'error'

export interface SwarmAgent {
  profile: AgentProfile
  state: AgentState
  lastActiveAt?: Date
  totalTurns: number
  errorCount: number
}

// ─── Topology ────────────────────────────────────────────────────

export type SwarmTopology = 'sequential' | 'hierarchical' | 'router'

export interface TopologyConfig {
  type: SwarmTopology
  sequential?: SequentialConfig
  hierarchical?: HierarchicalConfig
  router?: RouterConfig
}

export interface SequentialConfig {
  order: string[]
  passContext: boolean
  stopOnError: boolean
}

export interface HierarchicalConfig {
  managerId: string
  workerIds: string[]
  delegationStrategy: 'auto' | 'manual'
}

export interface RouterConfig {
  routingField: string
  defaultAgentId?: string
  fallbackStrategy: 'error' | 'route_random' | 'route_first'
}

// ─── Tasks ───────────────────────────────────────────────────────

export type TaskStatus = 'pending' | 'assigned' | 'running' | 'completed' | 'failed'

export interface SwarmTask {
  id: string
  description: string
  input: string
  assignedAgentId?: string
  status: TaskStatus
  result?: AgentTurnResult
  error?: string
  parentTaskId?: string
  subtasks: SwarmTask[]
  priority: number
  createdAt: Date
  startedAt?: Date
  completedAt?: Date
  metadata?: Record<string, unknown>
}

// ─── Run ─────────────────────────────────────────────────────────

export type SwarmRunStatus = 'pending' | 'running' | 'completed' | 'failed' | 'cancelled'

export interface SwarmRun {
  id: string
  name: string
  topology: SwarmTopology
  status: SwarmRunStatus
  tasks: SwarmTask[]
  agents: string[]
  startedAt?: Date
  completedAt?: Date
  totalTokens?: number
  error?: string
  metadata?: Record<string, unknown>
}

// ─── Config ──────────────────────────────────────────────────────

export interface SwarmOrchestratorConfig {
  maxConcurrentAgents: number
  defaultMaxTurns: number
  storeRunHistory: boolean
}

// ─── Delegation ─────────────────────────────────────────────────

export interface DelegationResult {
  taskId: string
  agentId: string
  confidence: number
  reason: string
}
