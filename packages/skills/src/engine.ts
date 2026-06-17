import { existsSync, mkdirSync } from 'node:fs'
import { SkillRegistry } from './registry.js'
import { SkillLoader } from './loader.js'
import { createSkillSandbox, evaluateSkillTrigger, validateSkillTools, buildSkillPrompt } from './sandbox.js'
import type { SkillInstance, SkillSandbox, SkillsEngineConfig, SkillsActiveSet, SkillState } from './types.js'
import type { SkillInjection } from '@hercules/core'

export class SkillsEngine {
  readonly registry: SkillRegistry
  readonly loader: SkillLoader
  private config: SkillsEngineConfig
  private sandboxes: Map<string, SkillSandbox> = new Map()

  constructor(config: Partial<SkillsEngineConfig> = {}) {
    this.config = {
      skillsDir: config.skillsDir ?? './skills',
      autoActivateOnStartup: config.autoActivateOnStartup ?? true,
      maxActiveSkills: config.maxActiveSkills ?? 5,
      conflictResolution: config.conflictResolution ?? 'priority',
    }

    this.registry = new SkillRegistry()
    this.loader = new SkillLoader({ skillsDir: this.config.skillsDir, registry: this.registry })
  }

  async initialize(): Promise<void> {
    if (!existsSync(this.config.skillsDir)) {
      mkdirSync(this.config.skillsDir, { recursive: true })
    }

    const loaded = await this.loader.loadAll()

    if (this.config.autoActivateOnStartup && loaded > 0) {
      for (const skill of this.registry.list()) {
        const hasStartupTrigger = skill.manifest.triggers.some(t => t.event === 'startup:after')
        if (hasStartupTrigger || skill.manifest.triggers.length === 0) {
          await this.activateSkill(skill.manifest.name)
        }
      }
    }
  }

  async activateSkill(name: string): Promise<SkillInstance> {
    const skill = this.registry.get(name)
    if (!skill) throw new Error(`Skill "${name}" not found`)

    const activeCount = this.registry.list({ state: 'active' }).length
    if (activeCount >= this.config.maxActiveSkills) {
      const resolution = this.config.conflictResolution

      if (resolution === 'priority') {
        const lowestPriority = this.registry.list({ state: 'active' })
          .sort((a, b) => a.manifest.priority - b.manifest.priority)[0]

        if (!lowestPriority || skill.manifest.priority <= lowestPriority.manifest.priority) {
          throw new Error(`Max active skills (${this.config.maxActiveSkills}) reached, and "${name}" priority (${skill.manifest.priority}) is not high enough to displace active skills`)
        }

        await this.deactivateSkill(lowestPriority.manifest.name)
      } else if (resolution === 'error') {
        throw new Error(`Max active skills (${this.config.maxActiveSkills}) reached`)
      }
    }

    this.registry.updateState(name, 'active')
    const sandbox = createSkillSandbox(skill)
    this.sandboxes.set(name, sandbox)

    return this.registry.get(name)!
  }

  async deactivateSkill(name: string): Promise<SkillInstance> {
    this.registry.updateState(name, 'inactive')
    this.sandboxes.delete(name)
    return this.registry.get(name)!
  }

  async evaluateAndActivate(eventName: string, input: string): Promise<SkillsActiveSet> {
    const candidates = this.registry.findByTrigger(eventName)

    for (const skill of candidates) {
      if (skill.state === 'active' || skill.state === 'disabled') continue
      if (!this.sandboxes.has(skill.manifest.name)) {
        this.sandboxes.set(skill.manifest.name, createSkillSandbox(skill))
      }

      const result = evaluateSkillTrigger(skill, eventName, input)
      if (result.shouldActivate) {
        try {
          await this.activateSkill(skill.manifest.name)
        } catch {
          // skill activation failed, move on
        }
      }
    }

    return this.getActiveSet()
  }

  getActiveSet(): SkillsActiveSet {
    const active = this.registry.list({ state: 'active' })
      .sort((a, b) => b.manifest.priority - a.manifest.priority)

    const injections: SkillInjection[] = active.map(s => ({
      name: s.manifest.name,
      content: buildSkillPrompt(s),
      priority: s.manifest.priority,
    }))

    return { active, injections, timestamp: new Date() }
  }

  getSandbox(name: string): SkillSandbox | undefined {
    return this.sandboxes.get(name)
  }

  validateRequiredTools(availableTools: string[]): Map<string, string[]> {
    const result = new Map<string, string[]>()
    for (const skill of this.registry.list()) {
      const missing = validateSkillTools(skill, availableTools)
      if (missing.length > 0) {
        result.set(skill.manifest.name, missing)
      }
    }
    return result
  }

  async reloadSkill(name: string): Promise<SkillInstance | null> {
    const wasActive = this.registry.get(name)?.state === 'active'

    if (wasActive) {
      await this.deactivateSkill(name)
    }

    this.registry.remove(name)
    const manifest = await this.loader.loadSingle(name)

    if (manifest && wasActive) {
      await this.activateSkill(name)
    }

    return manifest ? this.registry.get(name)! : null
  }

  async disableSkill(name: string): Promise<SkillInstance> {
    await this.deactivateSkill(name)
    return this.registry.updateState(name, 'disabled')
  }

  getMetrics(): { total: number; active: number; inactive: number; error: number; disabled: number } {
    const all = this.registry.list()
    return {
      total: all.length,
      active: all.filter(s => s.state === 'active').length,
      inactive: all.filter(s => s.state === 'inactive').length,
      error: all.filter(s => s.state === 'error').length,
      disabled: all.filter(s => s.state === 'disabled').length,
    }
  }
}
