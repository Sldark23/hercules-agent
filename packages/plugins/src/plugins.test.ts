import { describe, it, expect, beforeEach, afterEach } from 'vitest'
import { PluginRegistry } from './registry.js'
import { HookSystem, HOOK_NAMES } from './hooks/index.js'
import { PluginLoader } from './loader/index.js'
import { createSDK, definePlugin } from './sdk/index.js'
import { ToolRegistry } from '@hercules/tools'
import { mkdir, writeFile, rm } from 'node:fs/promises'
import { join } from 'node:path'
import { tmpdir } from 'node:os'
import { randomUUID } from 'node:crypto'
import type { PluginManifest } from './types.js'

// ─── PluginRegistry ────────────────────────────────────────────────

describe('PluginRegistry', () => {
  let registry: PluginRegistry

  beforeEach(() => { registry = new PluginRegistry() })

  it('registers a plugin from manifest', () => {
    const manifest: PluginManifest = { name: 'test', version: '1.0.0', description: '', entry: 'index.js', type: 'tool' }
    registry.register(manifest, '/tmp/test')
    expect(registry.get('test')).toBeDefined()
    expect(registry.count()).toBe(1)
  })

  it('throws on duplicate registration', () => {
    const m: PluginManifest = { name: 'dup', version: '1.0.0', description: '', entry: 'index.js', type: 'tool' }
    registry.register(m, '/tmp/dup')
    expect(() => registry.register(m, '/tmp/dup')).toThrow('already registered')
  })

  it('lists plugins by type', () => {
    registry.register({ name: 'a', version: '1.0.0', description: '', entry: 'i.js', type: 'tool' }, '/p/a')
    registry.register({ name: 'b', version: '1.0.0', description: '', entry: 'i.js', type: 'channel' }, '/p/b')
    expect(registry.list('tool')).toHaveLength(1)
    expect(registry.list('channel')).toHaveLength(1)
  })

  it('updates plugin state', () => {
    registry.register({ name: 't', version: '1.0.0', description: '', entry: 'i.js', type: 'tool' }, '/p/t')
    registry.updateState('t', 'active')
    expect(registry.get('t')?.state).toBe('active')
  })

  it('finds plugins by hook name', () => {
    registry.register({ name: 'h', version: '1.0.0', description: '', entry: 'i.js', type: 'hook', hooks: ['agent:before_turn'] }, '/p/h')
    expect(registry.findByHook('agent:before_turn')).toHaveLength(1)
  })
})

// ─── HookSystem ─────────────────────────────────────────────────────

describe('HookSystem', () => {
  let hooks: HookSystem

  beforeEach(() => { hooks = new HookSystem() })

  it('registers and dispatches hooks', async () => {
    let called = false
    hooks.register({ name: 'agent:before_turn', handler: () => { called = true }, pluginId: 'test', priority: 0, phase: 'before' })
    await hooks.dispatch('agent:before_turn', { sessionId: 's1', userInput: 'hi' })
    expect(called).toBe(true)
  })

  it('supports transform hooks', async () => {
    hooks.register({
      name: 'agent:before_turn',
      handler: (payload) => ({ ...(payload as object), userInput: 'transformed' }),
      pluginId: 'test', priority: 0, phase: 'before',
    })
    const result = await hooks.dispatch('agent:before_turn', { sessionId: 's1', userInput: 'hi' }, { transform: true })
    expect((result as { userInput: string }).userInput).toBe('transformed')
  })

  it('respects priority order', async () => {
    const order: number[] = []
    hooks.register({ name: 'agent:before_turn', handler: () => { order.push(2) }, pluginId: 'b', priority: 10, phase: 'before' })
    hooks.register({ name: 'agent:before_turn', handler: () => { order.push(1) }, pluginId: 'a', priority: 20, phase: 'before' })
    await hooks.dispatch('agent:before_turn', { sessionId: 's1', userInput: 'hi' })
    expect(order).toEqual([1, 2])
  })

  it('supports abort', async () => {
    let secondCalled = false
    hooks.register({ name: 'agent:before_turn', handler: (_, ctx) => { ctx.abort() }, pluginId: 'a', priority: 10, phase: 'before' })
    hooks.register({ name: 'agent:before_turn', handler: () => { secondCalled = true }, pluginId: 'b', priority: 0, phase: 'before' })
    await hooks.dispatch('agent:before_turn', { sessionId: 's1', userInput: 'hi' })
    expect(secondCalled).toBe(false)
  })

  it('unregisters all hooks for a plugin', () => {
    hooks.register({ name: 'agent:before_turn', handler: () => {}, pluginId: 'p1', priority: 0, phase: 'before' })
    hooks.register({ name: 'agent:after_turn', handler: () => {}, pluginId: 'p1', priority: 0, phase: 'after' })
    hooks.unregisterAll('p1')
    expect(hooks.count()).toBe(0)
  })
})

// ─── PluginLoader ───────────────────────────────────────────────────

describe('PluginLoader', () => {
  const testDir = join(tmpdir(), `hercules-plugin-test-${randomUUID().slice(0, 8)}`)
  const pluginDir = join(testDir, 'plugins')

  beforeEach(async () => {
    await rm(testDir, { recursive: true, force: true })
    await mkdir(pluginDir, { recursive: true })
  })

  it('skips directories without plugin manifest', async () => {
    await mkdir(join(pluginDir, 'no-manifest'), { recursive: true })
    const reg = new PluginRegistry()
    const hooks = new HookSystem()
    const loader = new PluginLoader(reg, hooks, { pluginDirs: [pluginDir] })

    const instances = await loader.loadAll()
    expect(instances).toHaveLength(0)
  })

  it('loads bundled plugins', async () => {
    const reg = new PluginRegistry()
    const hooks = new HookSystem()
    const loader = new PluginLoader(reg, hooks, {
      pluginDirs: [],
      bundledPlugins: [{ manifest: { name: 'bundled', version: '1.0.0', description: '', entry: 'i.js', type: 'tool' }, exports: { hello: 'world' } }],
    })

    const instances = await loader.loadAll()
    expect(instances).toHaveLength(1)
    expect(reg.get('bundled')?.exports.hello).toBe('world')
  })
})

// ─── PluginSDK ──────────────────────────────────────────────────────

describe('PluginSDK', () => {
  it('creates SDK with plugin context', () => {
    const registry = new ToolRegistry()
    const hooks = new HookSystem()
    const sdk = createSDK({ pluginId: 'my-plugin@1.0.0', hooks, registry })
    expect(sdk.pluginId).toBe('my-plugin@1.0.0')
  })

  it('registers tools via SDK', () => {
    const registry = new ToolRegistry()
    const hooks = new HookSystem()
    const sdk = createSDK({ pluginId: 'p1', hooks, registry })

    sdk.registerTool({
      name: 'plugin_tool', description: '', inputSchema: {} as any,
      handler: async () => ({ toolCallId: '', output: 'ok' }),
    })
    expect(sdk.getTool('plugin_tool')).toBeDefined()
    expect(sdk.listTools()).toHaveLength(1)
  })

  it('definePlugin wraps a function', () => {
    const fn = definePlugin((sdk) => { sdk.registerHook('agent:before_turn', () => {}) })
    expect(typeof fn).toBe('function')
  })
})
