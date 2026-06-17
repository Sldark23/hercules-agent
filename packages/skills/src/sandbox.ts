import { randomUUID } from 'node:crypto'
import type { SkillInstance, SkillManifest, SkillSandbox, SkillSandboxConfig, SkillEvaluationResult } from './types.js'

export function createSkillSandbox(
  skill: SkillInstance,
  overrides?: Partial<SkillSandboxConfig>
): SkillSandbox {
  const config: SkillSandboxConfig = {
    allowedTools: skill.manifest.tools,
    allowedHooks: skill.manifest.hooks,
    skillConfig: (skill.manifest.config as Record<string, unknown>) ?? {},
    sandboxId: randomUUID(),
    ...overrides,
  }

  return {
    id: config.sandboxId,
    skillName: skill.manifest.name,
    config,
    isToolAllowed(name: string): boolean {
      if (config.allowedTools.length === 0) return true
      return config.allowedTools.includes(name)
    },
    isHookAllowed(name: string): boolean {
      if (config.allowedHooks.length === 0) return true
      return config.allowedHooks.includes(name)
    },
  }
}

export function evaluateSkillTrigger(
  skill: SkillManifest | SkillInstance,
  eventName: string,
  input: string
): SkillEvaluationResult {
  const manifest = 'manifest' in skill ? skill.manifest : skill
  const matchedTriggers = manifest.triggers.filter(t => t.event === eventName)

  if (matchedTriggers.length === 0) {
    return { shouldActivate: false, confidence: 0, matchedTriggers: [] }
  }

  let confidence = 0

  for (const t of matchedTriggers) {
    if (t.pattern && input) {
      const regex = new RegExp(t.pattern, 'i')
      if (regex.test(input)) {
        confidence = Math.max(confidence, 0.8)
      }
    }

    if (t.keywords && input) {
      const lower = input.toLowerCase()
      const matched = t.keywords.filter(k => lower.includes(k.toLowerCase()))
      if (matched.length > 0) {
        confidence = Math.max(confidence, matched.length / t.keywords.length)
      }
    }
  }

  const hasContentTriggers = matchedTriggers.some(t => t.pattern || (t.keywords && t.keywords.length > 0))
  if (matchedTriggers.length > 0 && !hasContentTriggers) {
    confidence = 1.0
  }

  return {
    shouldActivate: confidence >= 0.3,
    confidence,
    matchedTriggers,
  }
}

export function validateSkillTools(
  skill: SkillInstance,
  availableTools: string[]
): string[] {
  const missing: string[] = []
  for (const tool of skill.manifest.tools) {
    if (!availableTools.includes(tool)) {
      missing.push(tool)
    }
  }
  return missing
}

export function buildSkillPrompt(skill: SkillInstance): string {
  const parts: string[] = []

  if (skill.manifest.prompt) {
    parts.push(skill.manifest.prompt)
  }

  if (skill.manifest.tools.length > 0) {
    parts.push(`Available tools: ${skill.manifest.tools.join(', ')}`)
  }

  return parts.join('\n\n')
}
