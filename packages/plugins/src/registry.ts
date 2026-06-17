import type { PluginInstance, PluginManifest, PluginState, PluginType } from './types.js'

export class PluginRegistry {
  private plugins: Map<string, PluginInstance> = new Map()
  private typeIndex: Map<PluginType, Set<string>> = new Map()

  register(manifest: PluginManifest, path: string): PluginInstance {
    if (this.plugins.has(manifest.name)) {
      throw new Error(`Plugin "${manifest.name}" is already registered`)
    }

    const instance: PluginInstance = {
      id: `${manifest.name}@${manifest.version}`,
      manifest,
      state: 'registered',
      path,
      exports: {},
      hooks: {},
      loadedAt: new Date(),
    }

    this.plugins.set(instance.id, instance)
    this.plugins.set(manifest.name, instance)

    const typeSet = this.typeIndex.get(manifest.type) ?? new Set()
    typeSet.add(instance.id)
    this.typeIndex.set(manifest.type, typeSet)

    return instance
  }

  get(idOrName: string): PluginInstance | undefined {
    return this.plugins.get(idOrName)
  }

  has(idOrName: string): boolean {
    return this.plugins.has(idOrName)
  }

  list(type?: PluginType): PluginInstance[] {
    if (type) {
      const ids = this.typeIndex.get(type) ?? new Set()
      return Array.from(ids).map(id => this.plugins.get(id)!).filter(Boolean)
    }
    return Array.from(this.plugins.values())
      .filter((v, i, a) => a.findIndex(p => p.manifest.name === v.manifest.name) === i)
  }

  listByType(): Map<PluginType, PluginInstance[]> {
    const result = new Map<PluginType, PluginInstance[]>()
    for (const [type, ids] of this.typeIndex) {
      result.set(type, Array.from(ids).map(id => this.plugins.get(id)!).filter(Boolean))
    }
    return result
  }

  updateState(idOrName: string, state: PluginState, error?: string): void {
    const plugin = this.plugins.get(idOrName)
    if (plugin) {
      plugin.state = state
      if (error) plugin.error = error
    }
  }

  remove(idOrName: string): boolean {
    const plugin = this.plugins.get(idOrName)
    if (!plugin) return false

    this.plugins.delete(plugin.id)
    this.plugins.delete(plugin.manifest.name)

    const typeSet = this.typeIndex.get(plugin.manifest.type)
    typeSet?.delete(plugin.id)

    return true
  }

  count(type?: PluginType): number {
    if (type) return this.typeIndex.get(type)?.size ?? 0
    return new Set(this.list().map(p => p.manifest.name)).size
  }

  clear(): void {
    this.plugins.clear()
    this.typeIndex.clear()
  }

  findByHook(hookName: string): PluginInstance[] {
    return this.list().filter(p => p.manifest.hooks?.includes(hookName))
  }

  getErrors(): PluginInstance[] {
    return this.list().filter(p => p.state === 'error')
  }
}
