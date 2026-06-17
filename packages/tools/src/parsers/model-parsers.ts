import type { ToolCall } from '@hercules/core'

export interface ToolCallParser {
  name: string
  /**
   * Parse a model's response text/extracted data into structured tool calls.
   * Returns null if no tool calls are found.
   */
  parse(response: string): ToolCall[] | null
}

export class AnthropicParser implements ToolCallParser {
  name = 'anthropic'

  parse(response: string): ToolCall[] | null {
    const calls: ToolCall[] = []
    const regex = /<function_calls>\s*<invoke name="([^"]+)">([\s\S]*?)<\/invoke>\s*<\/function_calls>/g
    let match: RegExpExecArray | null

    while ((match = regex.exec(response)) !== null) {
      const name = match[1]!
      const argsText = match[2]!.trim()
      try {
        const args = JSON.parse(argsText)
        calls.push({ id: `toolu_${Date.now()}_${calls.length}`, name, arguments: args })
      } catch {
        calls.push({ id: `toolu_${Date.now()}_${calls.length}`, name, arguments: { raw: argsText } })
      }
    }

    return calls.length > 0 ? calls : null
  }
}

export class OpenAIParser implements ToolCallParser {
  name = 'openai'

  parse(response: string): ToolCall[] | null {
    const calls: ToolCall[] = []

    const jsonMatch = response.match(/```json\n?([\s\S]*?)```/)
    if (jsonMatch) {
      try {
        const parsed = JSON.parse(jsonMatch[1]!)
        if (Array.isArray(parsed)) {
          for (const item of parsed) {
            if (item.type === 'function' && item.function) {
              calls.push({
                id: item.id ?? `call_${Date.now()}_${calls.length}`,
                name: item.function.name,
                arguments: typeof item.function.arguments === 'string'
                  ? JSON.parse(item.function.arguments)
                  : item.function.arguments,
              })
            }
          }
        }
      } catch {}
    }

    const toolRegex = /\[TOOL_CALL\]\s*(\w+)\s*\n([\s\S]*?)(?=\[TOOL_CALL\]|$)/g
    let match: RegExpExecArray | null
    while ((match = toolRegex.exec(response)) !== null) {
      try {
        calls.push({
          id: `call_${Date.now()}_${calls.length}`,
          name: match[1]!,
          arguments: JSON.parse(match[2]!.trim()),
        })
      } catch {}
    }

    return calls.length > 0 ? calls : null
  }
}

export class DeepSeekParser implements ToolCallParser {
  name = 'deepseek'

  parse(response: string): ToolCall[] | null {
    const calls: ToolCall[] = []
    const regex = /<tool_call>\s*\n([\s\S]*?)\n\s*<\/tool_call>/g
    let match: RegExpExecArray | null

    while ((match = regex.exec(response)) !== null) {
      try {
        const content = match[1]!.trim()
        const parsed = JSON.parse(content)
        calls.push({
          id: `ds_${Date.now()}_${calls.length}`,
          name: parsed.name ?? 'unknown',
          arguments: parsed.arguments ?? parsed,
        })
      } catch {}
    }

    return calls.length > 0 ? calls : null
  }
}

export class QwenParser implements ToolCallParser {
  name = 'qwen'

  parse(response: string): ToolCall[] | null {
    const calls: ToolCall[] = []

    const regex = /<tool_call>([\s\S]*?)<\/tool_call>/g
    let match: RegExpExecArray | null
    while ((match = regex.exec(response)) !== null) {
      try {
        const content = match[1]!.trim()
        const obj = JSON.parse(content)
        calls.push({
          id: `qwen_${Date.now()}_${calls.length}`,
          name: obj.name ?? 'unknown',
          arguments: obj.arguments ?? {},
        })
      } catch {}
    }

    return calls.length > 0 ? calls : null
  }
}

export class LlamaParser implements ToolCallParser {
  name = 'llama'

  parse(response: string): ToolCall[] | null {
    const calls: ToolCall[] = []
    const regex = /{"function":\s*{"name":\s*"([^"]+)"\s*,\s*"parameters":\s*({[\s\S]*?})}/g
    let match: RegExpExecArray | null

    while ((match = regex.exec(response)) !== null) {
      try {
        calls.push({
          id: `llama_${Date.now()}_${calls.length}`,
          name: match[1]!,
          arguments: JSON.parse(match[2]!),
        })
      } catch {}
    }

    return calls.length > 0 ? calls : null
  }
}

export function getParser(modelId: string): ToolCallParser {
  const id = modelId.toLowerCase()
  if (id.includes('claude') || id.includes('anthropic')) return new AnthropicParser()
  if (id.includes('deepseek') || id.includes('deep-seek')) return new DeepSeekParser()
  if (id.includes('qwen')) return new QwenParser()
  if (id.includes('llama') || id.includes('hermes')) return new LlamaParser()
  return new OpenAIParser()
}
