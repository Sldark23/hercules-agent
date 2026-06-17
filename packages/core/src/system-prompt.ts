import type { SystemPromptConfig, Message, ToolDefinition } from './types.js'

export interface SystemPromptAssembly {
  system: string
  toolDefs: string
  constraints: string
}

export function assembleSystemPrompt(
  config: SystemPromptConfig,
  tools: ToolDefinition[],
  recentMessages?: Message[]
): SystemPromptAssembly {
  const parts: string[] = []

  parts.push(`# Persona\n\n${config.persona}`)

  if (config.memoryContext) {
    parts.push(`# Memory Context\n\n${config.memoryContext}`)
  }

  if (config.skills && config.skills.length > 0) {
    const sorted = [...config.skills].sort((a, b) => b.priority - a.priority)
    parts.push(`# Active Skills\n\n${sorted.map(s => `## ${s.name}\n${s.content}`).join('\n\n')}`)
  }

  if (config.dynamicSections && config.dynamicSections.length > 0) {
    for (const section of config.dynamicSections) {
      parts.push(`# ${section.name}\n\n${section.content}`)
    }
  }

  const toolDefs = tools.length > 0
    ? `# Available Tools\n\n${tools.map(t => {
        const schema = JSON.stringify(t.inputSchema, null, 2)
        return `## ${t.name}\n${t.description}\n\nParameters:\n\`\`\`json\n${schema}\n\`\`\``
      }).join('\n\n')}`
    : ''

  if (toolDefs) parts.push(toolDefs)

  if (config.toolInstructions) {
    parts.push(`# Tool Usage\n\n${config.toolInstructions}`)
  }

  const constraintsText = config.constraints?.length
    ? `# Constraints\n\n${config.constraints.map(c => `- ${c}`).join('\n')}`
    : ''

  if (constraintsText) parts.push(constraintsText)

  return {
    system: parts.join('\n\n---\n\n'),
    toolDefs,
    constraints: constraintsText,
  }
}
