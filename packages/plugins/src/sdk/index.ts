import { HookSystem, HOOK_NAMES } from '../hooks/index.js'
import type { HookName, HookHandler, HookPhase, HookContext } from '../hooks/index.js'
import { ToolRegistry } from '@hercules/tools'
import type { RegisteredTool, ToolHandler } from '@hercules/tools'
import type { PluginManifest } from '../types.js'

export interface PluginSDK {
  pluginId: string
  hooks: HookSystem
  registry: ToolRegistry

  registerHook(
    name: HookName,
    handler: HookHandler,
    options?: { priority?: number; phase?: HookPhase }
  ): void

  registerTool(tool: RegisteredTool): void
  registerTools(tools: RegisteredTool[]): void

  getTool(name: string): RegisteredTool | undefined
  listTools(category?: string): RegisteredTool[]
}

export function createSDK(opts: {
  pluginId: string
  hooks: HookSystem
  registry: ToolRegistry
}): PluginSDK {
  return {
    pluginId: opts.pluginId,
    hooks: opts.hooks,
    registry: opts.registry,

    registerHook(name, handler, options = {}) {
      opts.hooks.register({
        name,
        handler,
        pluginId: opts.pluginId,
        priority: options.priority ?? 0,
        phase: options.phase ?? 'after',
      })
    },

    registerTool(tool: RegisteredTool) {
      opts.registry.register(tool)
    },

    registerTools(tools: RegisteredTool[]) {
      opts.registry.registerBatch(tools)
    },

    getTool(name: string) {
      return opts.registry.get(name)
    },

    listTools(category?: string) {
      return opts.registry.list(category)
    },
  }
}

export type PluginEntry = (sdk: PluginSDK) => void | Promise<void>

export function definePlugin(fn: PluginEntry): PluginEntry {
  return fn
}

export { HOOK_NAMES }
export type { HookName, HookHandler, HookPhase, HookContext, RegisteredTool, ToolHandler, PluginManifest }
