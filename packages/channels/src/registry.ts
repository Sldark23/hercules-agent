import type { ChannelAdapter, ChannelEvent, ChannelEventHandler } from './types.js'

export class ChannelRegistry {
  private adapters: Map<string, ChannelAdapter> = new Map()
  private typeIndex: Map<string, Set<string>> = new Map()
  private handlers: ChannelEventHandler[] = []

  register(adapter: ChannelAdapter): void {
    if (this.adapters.has(adapter.name)) {
      throw new Error(`Channel "${adapter.name}" is already registered`)
    }
    this.adapters.set(adapter.name, adapter)

    const typeSet = this.typeIndex.get(adapter.type) ?? new Set()
    typeSet.add(adapter.name)
    this.typeIndex.set(adapter.type, typeSet)

    adapter.on((event) => this.dispatch(event))
  }

  get(name: string): ChannelAdapter | undefined {
    return this.adapters.get(name)
  }

  list(type?: string): ChannelAdapter[] {
    if (type) {
      const names = this.typeIndex.get(type) ?? new Set()
      return Array.from(names).map(n => this.adapters.get(n)!).filter(Boolean)
    }
    return Array.from(this.adapters.values())
  }

  listTypes(): string[] {
    return Array.from(this.typeIndex.keys())
  }

  remove(name: string): boolean {
    const adapter = this.adapters.get(name)
    if (!adapter) return false

    this.adapters.delete(name)
    const typeSet = this.typeIndex.get(adapter.type)
    typeSet?.delete(name)
    return true
  }

  on(handler: ChannelEventHandler): () => void {
    this.handlers.push(handler)
    return () => {
      this.handlers = this.handlers.filter(h => h !== handler)
    }
  }

  async startAll(): Promise<void> {
    for (const adapter of this.adapters.values()) {
      try { await adapter.start() }
      catch (err) { console.error(`[channels] Failed to start "${adapter.name}":`, err) }
    }
  }

  async stopAll(): Promise<void> {
    for (const adapter of this.adapters.values()) {
      try { await adapter.stop() }
      catch (err) { console.error(`[channels] Failed to stop "${adapter.name}":`, err) }
    }
  }

  count(): number {
    return this.adapters.size
  }

  private dispatch(event: ChannelEvent): void {
    for (const handler of this.handlers) {
      try { handler(event) }
      catch (err) { console.error('[channels] Handler error:', err) }
    }
  }
}
