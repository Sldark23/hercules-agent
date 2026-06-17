import type { AgentEvent, ToolCall, ToolResult, Message } from '@hercules/core'
import type { PluginInstance } from '../types.js'

export type HookPhase = 'before' | 'after' | 'on' | 'instead'

export interface HookContext {
  pluginId: string
  pluginName: string
  timestamp: Date
  abort(): void
}

export type HookHandler<T = unknown> = (
  payload: T,
  ctx: HookContext
) => T | Promise<T> | void | Promise<void>

export interface HookRegistration {
  name: string
  handler: HookHandler
  pluginId: string
  priority: number
  phase: HookPhase
}

export const HOOK_NAMES = [
  'agent:before_turn',
  'agent:after_turn',
  'agent:before_tool_call',
  'agent:after_tool_call',
  'agent:before_message',
  'agent:after_message',
  'agent:on_event',
  'session:before_create',
  'session:after_create',
  'session:before_destroy',
  'plugin:before_load',
  'plugin:after_load',
  'plugin:before_unload',
  'plugin:after_unload',
  'config:before_apply',
  'config:after_apply',
  'startup:before',
  'startup:after',
  'shutdown:before',
  'shutdown:after',
] as const

export type HookName = (typeof HOOK_NAMES)[number]

export interface AgentBeforeTurnPayload { sessionId: string; userInput: string }
export interface AgentAfterTurnPayload { sessionId: string; result: unknown }
export interface AgentBeforeToolCallPayload { toolCall: ToolCall }
export interface AgentAfterToolCallPayload { toolCall: ToolCall; result: ToolResult }
export interface AgentBeforeMessagePayload { message: Message }
export interface AgentAfterMessagePayload { message: Message }
export interface AgentEventPayload { event: AgentEvent }
export interface SessionBeforeCreatePayload { sessionId: string; userId?: string }
export interface SessionAfterCreatePayload { sessionId: string; userId?: string }
export interface PluginBeforeLoadPayload { manifest: { name: string; version: string } }
export interface PluginAfterLoadPayload { instance: PluginInstance }

export class HookSystem {
  private hooks: Map<string, HookRegistration[]> = new Map()
  private aborted = false

  register(hook: HookRegistration): void {
    const existing = this.hooks.get(hook.name) ?? []
    existing.push(hook)
    existing.sort((a, b) => b.priority - a.priority)
    this.hooks.set(hook.name, existing)
  }

  unregister(name: string, pluginId: string): boolean {
    const existing = this.hooks.get(name)
    if (!existing) return false
    const filtered = existing.filter(h => h.pluginId !== pluginId)
    if (filtered.length === 0) this.hooks.delete(name)
    else this.hooks.set(name, filtered)
    return true
  }

  unregisterAll(pluginId: string): void {
    for (const [name, handlers] of this.hooks) {
      const filtered = handlers.filter(h => h.pluginId !== pluginId)
      if (filtered.length === 0) this.hooks.delete(name)
      else this.hooks.set(name, filtered)
    }
  }

  async dispatch<T>(
    name: HookName,
    payload: T,
    options: { abortOnError?: boolean; transform?: boolean } = {}
  ): Promise<T> {
    const handlers = this.hooks.get(name)
    if (!handlers || handlers.length === 0) return payload

    this.aborted = false
    let current = payload

    for (const handler of handlers) {
      if (this.aborted) break

      const ctx: HookContext = {
        pluginId: handler.pluginId,
        pluginName: handler.pluginId.split('@')[0]!,
        timestamp: new Date(),
        abort: () => { this.aborted = true },
      }

      try {
        if (options.transform) {
          const result = await handler.handler(current, ctx)
          if (result !== undefined) current = result as T
        } else {
          await handler.handler(current, ctx)
        }
      } catch (err) {
        if (options.abortOnError) throw err
        console.error(`[hooks] Error in "${name}" handler from ${handler.pluginId}:`, err)
      }
    }

    return current
  }

  async dispatchParallel<T>(name: HookName, payload: T): Promise<void> {
    const handlers = this.hooks.get(name)
    if (!handlers) return

    await Promise.all(handlers.map(handler =>
      Promise.resolve(handler.handler(payload, {
        pluginId: handler.pluginId,
        pluginName: handler.pluginId.split('@')[0]!,
        timestamp: new Date(),
        abort: () => {},
      })).catch((err: unknown) => {
        console.error(`[hooks] Error in "${name}" handler from ${handler.pluginId}:`, err)
      })
    ))
  }

  hasHandlers(name: HookName): boolean {
    return (this.hooks.get(name)?.length ?? 0) > 0
  }

  count(name?: HookName): number {
    if (name) return this.hooks.get(name)?.length ?? 0
    let total = 0
    for (const handlers of this.hooks.values()) total += handlers.length
    return total
  }

  clear(): void {
    this.hooks.clear()
    this.aborted = false
  }
}
