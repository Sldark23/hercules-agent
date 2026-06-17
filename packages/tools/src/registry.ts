import { z } from 'zod'
import type { ToolDefinition, ToolContext, ToolResult } from '@hercules/core'

export type ToolHandler = (input: unknown, ctx: ToolContext) => Promise<ToolResult>

export interface RegisteredTool {
  name: string
  description: string
  inputSchema: z.ZodType
  handler: ToolHandler
  category?: string
  requiresApproval?: boolean
  timeout?: number
}

export class ToolRegistry {
  private tools: Map<string, RegisteredTool> = new Map()
  private aliases: Map<string, string> = new Map()

  register(tool: RegisteredTool): void {
    if (this.tools.has(tool.name)) {
      throw new Error(`Tool "${tool.name}" is already registered`)
    }
    this.tools.set(tool.name, { ...tool, requiresApproval: tool.requiresApproval ?? false })
  }

  registerBatch(tools: RegisteredTool[]): void {
    for (const t of tools) this.register(t)
  }

  get(name: string): RegisteredTool | undefined {
    const resolved = this.aliases.get(name) ?? name
    return this.tools.get(resolved)
  }

  has(name: string): boolean {
    return this.tools.has(name) || this.aliases.has(name)
  }

  list(category?: string): RegisteredTool[] {
    const all = Array.from(this.tools.values())
    return category ? all.filter(t => t.category === category) : all
  }

  listNames(category?: string): string[] {
    return this.list(category).map(t => t.name)
  }

  alias(alias: string, target: string): void {
    if (!this.tools.has(target)) {
      throw new Error(`Cannot alias "${alias}" → "${target}": target not registered`)
    }
    this.aliases.set(alias, target)
  }

  remove(name: string): boolean {
    return this.tools.delete(name)
  }

  count(): number {
    return this.tools.size
  }

  clear(): void {
    this.tools.clear()
    this.aliases.clear()
  }

  toToolDefinitions(): ToolDefinition[] {
    return Array.from(this.tools.values()).map(t => ({
      name: t.name,
      description: t.description,
      inputSchema: t.inputSchema,
      handler: t.handler,
    }))
  }

  validate(name: string, input: unknown): { success: true; data: unknown } | { success: false; error: string } {
    const tool = this.tools.get(name)
    if (!tool) return { success: false, error: `Tool "${name}" not found` }

    const result = tool.inputSchema.safeParse(input)
    if (result.success) return { success: true, data: result.data }

    return {
      success: false,
      error: result.error.issues.map(i => `${i.path.join('.')}: ${i.message}`).join('; '),
    }
  }
}
