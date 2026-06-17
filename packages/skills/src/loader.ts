import { readFile, readdir } from 'node:fs/promises'
import { join, extname } from 'node:path'
import { existsSync } from 'node:fs'
import { SkillManifestSchema, type SkillManifest } from './types.js'
import type { SkillRegistry } from './registry.js'

const MANIFEST_CANDIDATES = [
  'hercules.skill.json', 'hercules.skill.yaml',
  'skill.json', 'skill.yaml', 'manifest.json',
]

export interface SkillLoaderConfig {
  skillsDir: string
  registry: SkillRegistry
}

export class SkillLoader {
  private config: SkillLoaderConfig

  constructor(config: SkillLoaderConfig) {
    this.config = config
  }

  async loadAll(): Promise<number> {
    if (!existsSync(this.config.skillsDir)) return 0

    const entries = await readdir(this.config.skillsDir, { withFileTypes: true })
    let count = 0

    for (const entry of entries) {
      if (!entry.isDirectory()) continue
      const skillDir = join(this.config.skillsDir, entry.name)
      const manifest = await this.loadManifestFromDir(skillDir)
      if (manifest) {
        this.config.registry.register(manifest, skillDir)
        count++
      }
    }

    return count
  }

  async loadSingle(name: string): Promise<SkillManifest | null> {
    const skillDir = join(this.config.skillsDir, name)
    if (!existsSync(skillDir)) return null

    const manifest = await this.loadManifestFromDir(skillDir)
    if (manifest) {
      this.config.registry.register(manifest, skillDir)
    }
    return manifest
  }

  private async loadManifestFromDir(dir: string): Promise<SkillManifest | null> {
    for (const candidate of MANIFEST_CANDIDATES) {
      const fullPath = join(dir, candidate)
      if (!existsSync(fullPath)) continue

      try {
        const content = await readFile(fullPath, 'utf-8')
        const ext = extname(fullPath)
        let parsed: unknown

        if (ext === '.json') {
          parsed = JSON.parse(content)
        } else if (ext === '.yaml') {
          throw new Error('YAML parsing not available - install js-yaml')
        }

        return SkillManifestSchema.parse(parsed)
      } catch (err) {
        const msg = err instanceof Error ? err.message : String(err)
        throw new Error(`Failed to load skill from ${fullPath}: ${msg}`)
      }
    }

    return null
  }

  async loadManifestFromContent(name: string, content: string, format: 'json' | 'yaml'): Promise<SkillManifest> {
    let parsed: unknown
    if (format === 'json') {
      parsed = JSON.parse(content)
    } else {
      throw new Error('YAML parsing not available - install js-yaml')
    }
    return SkillManifestSchema.parse(parsed)
  }

  async discoverSkills(): Promise<string[]> {
    if (!existsSync(this.config.skillsDir)) return []

    const entries = await readdir(this.config.skillsDir, { withFileTypes: true })
    const skillNames: string[] = []

    for (const entry of entries) {
      if (!entry.isDirectory()) continue
      const skillDir = join(this.config.skillsDir, entry.name)
      const hasManifest = MANIFEST_CANDIDATES.some(c => existsSync(join(skillDir, c)))
      if (hasManifest) skillNames.push(entry.name)
    }

    return skillNames
  }
}
