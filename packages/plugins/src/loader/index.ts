import { readFile, access } from 'node:fs/promises'
import { join, resolve } from 'node:path'
import { existsSync } from 'node:fs'
import { PluginManifestSchema } from '../types.js'
import type { PluginInstance, PluginManifest } from '../types.js'
import { PluginRegistry } from '../registry.js'
import { HookSystem } from '../hooks/index.js'
import type { HookHandler } from '../hooks/index.js'

export interface LoaderConfig {
  pluginDirs: string[]
  bundledPlugins?: Array<{ manifest: PluginManifest; exports: Record<string, unknown> }>
}

export class PluginLoader {
  private registry: PluginRegistry
  private hooks: HookSystem
  private config: LoaderConfig

  constructor(registry: PluginRegistry, hooks: HookSystem, config: LoaderConfig) {
    this.registry = registry
    this.hooks = hooks
    this.config = config
  }

  async loadAll(): Promise<PluginInstance[]> {
    const results: PluginInstance[] = []

    if (this.config.bundledPlugins) {
      for (const bp of this.config.bundledPlugins) {
        const instance = this.registry.register(bp.manifest, '(bundled)')
        instance.exports = bp.exports
        instance.state = 'active'
        results.push(instance)
      }
    }

    for (const dir of this.config.pluginDirs) {
      const instances = await this.loadFromDirectory(dir)
      results.push(...instances)
    }

    return results
  }

  async loadPlugin(name: string): Promise<PluginInstance> {
    for (const dir of this.config.pluginDirs) {
      const pluginDir = resolve(dir, name)
      if (!existsSync(pluginDir)) continue

      const manifestPath = join(pluginDir, 'hercules.plugin.json')
      if (!existsSync(manifestPath)) continue

      return this.loadSingle(pluginDir, manifestPath)
    }

    const npmPath = await this.resolveNpmPlugin(name)
    if (npmPath) return this.loadSingle(npmPath, join(npmPath, 'hercules.plugin.json'))

    throw new Error(`Plugin "${name}" not found in any plugin directory or npm`)
  }

  private async loadFromDirectory(dir: string): Promise<PluginInstance[]> {
    const results: PluginInstance[] = []
    const { readdir } = await import('node:fs/promises')

    try {
      const entries = await readdir(dir, { withFileTypes: true })
      for (const entry of entries) {
        if (!entry.isDirectory()) continue
        const pluginDir = join(dir, entry.name)
        const manifestPath = join(pluginDir, 'hercules.plugin.json')
        if (!existsSync(manifestPath)) continue

        try {
          const instance = await this.loadSingle(pluginDir, manifestPath)
          results.push(instance)
        } catch (err) {
          console.error(`[plugins] Failed to load ${entry.name}:`, err)
        }
      }
    } catch {}
    return results
  }

  private async loadSingle(pluginDir: string, manifestPath: string): Promise<PluginInstance> {
    await this.hooks.dispatch('plugin:before_load', {
      manifest: { name: manifestPath, version: '0.0.0' },
    })

    const content = await readFile(manifestPath, 'utf-8')
    const raw = JSON.parse(content)
    const manifest = PluginManifestSchema.parse(raw)

    const instance = this.registry.register(manifest, pluginDir)
    instance.state = 'loading'

    const entryPath = join(pluginDir, manifest.entry)
    if (existsSync(entryPath)) {
      try {
        const mod = await import(entryPath)
        instance.exports = mod

        if (typeof mod.register === 'function') {
          await mod.register({ pluginId: instance.id, hooks: this.hooks, registry: this.registry })
        }

        if (manifest.hooks) {
          for (const hookName of manifest.hooks) {
            const handlerName = `on${hookName.replace(/:/g, '_')}`
            if (typeof mod[handlerName] === 'function') {
              instance.hooks[hookName] = instance.hooks[hookName] ?? []
              instance.hooks[hookName]!.push(mod[handlerName])
            }
          }
        }
      } catch (err) {
        instance.state = 'error'
        instance.error = (err as Error).message
        await this.hooks.dispatch('plugin:after_load', { instance })
        throw err
      }
    }

    instance.state = 'active'
    instance.loadedAt = new Date()

    await this.hooks.dispatch('plugin:after_load', { instance })
    return instance
  }

  private async resolveNpmPlugin(_name: string): Promise<string | null> {
    try {
      const nodeModulesPath = join(process.cwd(), 'node_modules', `hercules-plugin-${_name}`)
      const altPath = join(process.cwd(), 'node_modules', _name)
      for (const p of [nodeModulesPath, altPath]) {
        if (existsSync(p) && existsSync(join(p, 'hercules.plugin.json'))) return p
      }
    } catch {}
    return null
  }
}
