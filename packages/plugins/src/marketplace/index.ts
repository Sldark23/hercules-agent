import { z } from 'zod'
import { execSync } from 'node:child_process'
import { join } from 'node:path'
import { existsSync, mkdirSync, writeFileSync, readFileSync } from 'node:fs'
import type { PluginMetadata, PluginManifest } from '../types.js'
import { PluginManifestSchema } from '../types.js'

export interface MarketplaceConfig {
  registryUrl: string
  installDir: string
  npmRegistry?: string
}

export interface PackageJson {
  name: string
  version: string
  description?: string
  hercules?: Partial<PluginManifest>
  [key: string]: unknown
}

export class Marketplace {
  private config: MarketplaceConfig
  private cache: Map<string, PluginMetadata[]> = new Map()

  constructor(config: MarketplaceConfig) {
    this.config = {
      registryUrl: config.registryUrl,
      installDir: config.installDir,
      npmRegistry: 'https://registry.npmjs.org',
    }
    if (!existsSync(config.installDir)) {
      mkdirSync(config.installDir, { recursive: true })
    }
  }

  async search(query: string, options?: { type?: string; limit?: number }): Promise<PluginMetadata[]> {
    try {
      const url = new URL('/api/plugins/search', this.config.registryUrl)
      url.searchParams.set('q', query)
      if (options?.type) url.searchParams.set('type', options.type)
      if (options?.limit) url.searchParams.set('limit', String(options.limit))

      const res = await fetch(url.toString())
      if (res.ok) return (await res.json()) as PluginMetadata[]
    } catch {}

    return []
  }

  async getInfo(name: string): Promise<PluginMetadata | null> {
    try {
      const npmName = `hercules-plugin-${name}`
      const url = `${this.config.npmRegistry}/${npmName}`
      const res = await fetch(url)
      if (!res.ok) return null

      const pkg = (await res.json()) as PackageJson
      return {
        id: npmName,
        name,
        version: pkg.version,
        description: pkg.description ?? '',
        type: pkg.hercules?.type ?? 'extension',
        source: 'registry',
      }
    } catch {}
    return null
  }

  async install(name: string, version?: string): Promise<PluginManifest> {
    const npmName = `hercules-plugin-${name}`
    const target = version ? `${npmName}@${version}` : npmName

    execSync(`npm install ${target} --prefix "${this.config.installDir}" --no-save`, {
      stdio: 'pipe',
      timeout: 120_000,
    })

    const nodeModules = join(this.config.installDir, 'node_modules', npmName)
    const manifestPath = join(nodeModules, 'hercules.plugin.json')
    const pkgPath = join(nodeModules, 'package.json')

    if (existsSync(manifestPath)) {
      const content = readFileSync(manifestPath, 'utf-8')
      return PluginManifestSchema.parse(JSON.parse(content))
    }

    if (existsSync(pkgPath)) {
      const pkg = JSON.parse(readFileSync(pkgPath, 'utf-8')) as PackageJson
      if (pkg.hercules) {
        const manifest: PluginManifest = {
          name: pkg.name,
          version: pkg.version,
          description: pkg.description ?? '',
          entry: pkg.hercules.entry ?? 'index.js',
          type: pkg.hercules.type ?? 'extension',
          ...pkg.hercules,
        }
        writeFileSync(manifestPath, JSON.stringify(manifest, null, 2))
        return PluginManifestSchema.parse(manifest)
      }
    }

    throw new Error(`No hercules.plugin.json found in ${npmName}. The package may not be a valid plugin.`)
  }

  async uninstall(name: string): Promise<void> {
    const npmName = `hercules-plugin-${name}`
    const pluginDir = join(this.config.installDir, 'node_modules', npmName)
    const installedDir = join(this.config.installDir, name)

    execSync(`npm uninstall ${npmName} --prefix "${this.config.installDir}" --no-save`, {
      stdio: 'pipe',
      timeout: 30_000,
    }).toString()

    const { rm } = await import('node:fs/promises')
    for (const dir of [pluginDir, installedDir]) {
      if (existsSync(dir)) await rm(dir, { recursive: true, force: true })
    }
  }

  async update(name: string): Promise<PluginManifest> {
    return this.install(name)
  }

  async listInstalled(): Promise<PluginMetadata[]> {
    const { readdir } = await import('node:fs/promises')
    const results: PluginMetadata[] = []

    const nodeModules = join(this.config.installDir, 'node_modules')
    if (!existsSync(nodeModules)) return results

    const dirs = await readdir(nodeModules)
    for (const dir of dirs) {
      if (!dir.startsWith('hercules-plugin-')) continue
      const pkgPath = join(nodeModules, dir, 'package.json')
      if (!existsSync(pkgPath)) continue

      try {
        const pkg = JSON.parse(readFileSync(pkgPath, 'utf-8')) as PackageJson
        results.push({
          id: dir,
          name: dir.replace('hercules-plugin-', ''),
          version: pkg.version,
          description: pkg.description ?? '',
          type: pkg.hercules?.type ?? 'extension',
          source: 'registry',
        })
      } catch {}
    }

    return results
  }

  async publish(_pluginDir: string): Promise<void> {
    throw new Error('Publishing is not yet implemented. Use npm publish directly.')
  }
}
