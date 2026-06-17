import type { SkillInstance, SkillManifest, SkillState } from './types.js'

export class SkillRegistry {
  private skills: Map<string, SkillInstance> = new Map()

  register(manifest: SkillManifest, path: string): SkillInstance {
    if (this.skills.has(manifest.name)) {
      throw new Error(`Skill "${manifest.name}" is already registered`)
    }

    const instance: SkillInstance = {
      id: `${manifest.name}@${manifest.version}`,
      manifest,
      state: 'inactive',
      path,
      loadedAt: new Date(),
    }

    this.skills.set(manifest.name, instance)
    return instance
  }

  get(name: string): SkillInstance | undefined {
    return this.skills.get(name)
  }

  has(name: string): boolean {
    return this.skills.has(name)
  }

  list(filter?: { state?: SkillState; tool?: string; hook?: string }): SkillInstance[] {
    let results = Array.from(this.skills.values())

    if (filter?.state) {
      results = results.filter(s => s.state === filter.state)
    }
    if (filter?.tool) {
      results = results.filter(s => s.manifest.tools.includes(filter.tool!))
    }
    if (filter?.hook) {
      results = results.filter(s => s.manifest.hooks.includes(filter.hook!))
    }

    return results
  }

  updateState(name: string, state: SkillState, error?: string): SkillInstance {
    const skill = this.skills.get(name)
    if (!skill) throw new Error(`Skill "${name}" not found`)

    skill.state = state
    if (error) skill.error = error
    return skill
  }

  remove(name: string): boolean {
    return this.skills.delete(name)
  }

  count(): number {
    return this.skills.size
  }

  clear(): void {
    this.skills.clear()
  }

  findByTrigger(eventName: string): SkillInstance[] {
    return Array.from(this.skills.values())
      .filter(s => s.manifest.triggers.some(t => t.event === eventName))
  }

  findConflicts(name: string): SkillInstance[] {
    const skill = this.skills.get(name)
    if (!skill) return []

    return Array.from(this.skills.values())
      .filter(s =>
        s.manifest.name !== name &&
        s.state === 'active' &&
        this.sharesTriggers(s, skill)
      )
  }

  private sharesTriggers(a: SkillInstance, b: SkillInstance): boolean {
    return a.manifest.triggers.some(ta =>
      b.manifest.triggers.some(tb => ta.event === tb.event)
    )
  }
}
