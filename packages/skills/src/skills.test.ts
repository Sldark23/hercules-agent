import { describe, it, expect, beforeEach, afterEach } from 'vitest'
import { mkdtempSync, writeFileSync, mkdirSync, rmSync, existsSync } from 'node:fs'
import { join } from 'node:path'
import { tmpdir } from 'node:os'
import { SkillRegistry } from './registry.js'
import { SkillLoader } from './loader.js'
import { createSkillSandbox, evaluateSkillTrigger, validateSkillTools, buildSkillPrompt } from './sandbox.js'
import { SkillsEngine } from './engine.js'
import type { SkillManifest } from './types.js'

const testDir = mkdtempSync(join(tmpdir(), 'skills-test-'))

function makeSkill(overrides: Partial<SkillManifest> = {}): SkillManifest {
  return {
    name: 'test-skill',
    version: '1.0.0',
    description: 'A test skill',
    author: 'test',
    tools: [],
    hooks: [],
    triggers: [],
    prompt: '',
    priority: 0,
    requires: [],
    ...overrides,
  }
}

// ─── SkillRegistry ───────────────────────────────────────────────

describe('SkillRegistry', () => {
  let registry: SkillRegistry

  beforeEach(() => { registry = new SkillRegistry() })

  it('registers a skill', () => {
    const inst = registry.register(makeSkill(), '/path')
    expect(inst.id).toBe('test-skill@1.0.0')
    expect(inst.state).toBe('inactive')
    expect(registry.count()).toBe(1)
  })

  it('throws on duplicate register', () => {
    registry.register(makeSkill(), '/p')
    expect(() => registry.register(makeSkill(), '/p')).toThrow('already registered')
  })

  it('gets skill by name', () => {
    registry.register(makeSkill(), '/p')
    expect(registry.get('test-skill')).toBeDefined()
    expect(registry.get('nonexistent')).toBeUndefined()
  })

  it('lists skills with filters', () => {
    const r1 = makeSkill({ name: 's1', tools: ['exec'] })
    const r2 = makeSkill({ name: 's2', hooks: ['agent:before_turn'] })
    const r3 = makeSkill({ name: 's3', tools: ['exec'], hooks: ['agent:before_turn'] })

    registry.register(r1, '/p1')
    registry.register(r2, '/p2')
    registry.register(r3, '/p3')

    expect(registry.list()).toHaveLength(3)
    expect(registry.list({ tool: 'exec' })).toHaveLength(2)
    expect(registry.list({ tool: 'browser' })).toHaveLength(0)
    expect(registry.list({ hook: 'agent:before_turn' })).toHaveLength(2)
  })

  it('updates skill state', () => {
    registry.register(makeSkill(), '/p')
    registry.updateState('test-skill', 'active')
    expect(registry.get('test-skill')!.state).toBe('active')
  })

  it('finds by trigger', () => {
    const s = makeSkill({ name: 'trigger-skill', triggers: [{ event: 'agent:before_turn' }] })
    registry.register(s, '/p')
    const found = registry.findByTrigger('agent:before_turn')
    expect(found).toHaveLength(1)
    expect(found[0]!.manifest.name).toBe('trigger-skill')
  })

  it('removes a skill', () => {
    registry.register(makeSkill(), '/p')
    expect(registry.remove('test-skill')).toBe(true)
    expect(registry.count()).toBe(0)
  })
})

// ─── SkillLoader ─────────────────────────────────────────────────

describe('SkillLoader', () => {
  let registry: SkillRegistry
  let loader: SkillLoader

  beforeEach(() => {
    registry = new SkillRegistry()
    loader = new SkillLoader({ skillsDir: join(testDir, 'skills'), registry })
    mkdirSync(join(testDir, 'skills', 'my-skill'), { recursive: true })
  })

  afterEach(() => {
    rmSync(join(testDir, 'skills'), { recursive: true, force: true })
  })

  it('loads a skill from manifest.json', async () => {
    writeFileSync(join(testDir, 'skills', 'my-skill', 'manifest.json'), JSON.stringify({
      name: 'loaded-skill',
      version: '1.0.0',
      description: 'Loaded from disk',
      triggers: [{ event: 'agent:before_turn', keywords: ['help'] }],
      tools: ['exec'],
      prompt: 'You are a helper.',
    }))

    const loaded = await loader.loadSingle('my-skill')
    expect(loaded).not.toBeNull()
    expect(loaded!.name).toBe('loaded-skill')
    expect(registry.get('loaded-skill')).toBeDefined()
  })

  it('loads all skills from directory', async () => {
    mkdirSync(join(testDir, 'skills', 'skill-a'), { recursive: true })
    mkdirSync(join(testDir, 'skills', 'skill-b'), { recursive: true })

    writeFileSync(join(testDir, 'skills', 'skill-a', 'manifest.json'), JSON.stringify({
      name: 'skill-a', version: '1.0.0',
    }))
    writeFileSync(join(testDir, 'skills', 'skill-b', 'manifest.json'), JSON.stringify({
      name: 'skill-b', version: '2.0.0',
    }))

    const count = await loader.loadAll()
    expect(count).toBe(2)
    expect(registry.get('skill-a')).toBeDefined()
    expect(registry.get('skill-b')).toBeDefined()
  })

  it('handles missing skills directory', async () => {
    const emptyLoader = new SkillLoader({ skillsDir: '/nonexistent/path', registry })
    const count = await emptyLoader.loadAll()
    expect(count).toBe(0)
  })

  it('loads manifest from raw JSON content', async () => {
    const manifest = await loader.loadManifestFromContent('inline', JSON.stringify({
      name: 'inline-skill', version: '2.1.0', description: 'inline',
    }), 'json')
    expect(manifest.name).toBe('inline-skill')
    expect(manifest.version).toBe('2.1.0')
  })
})

// ─── SkillSandbox ────────────────────────────────────────────────

describe('SkillSandbox', () => {
  it('creates sandbox with allowed tools', () => {
    const skill = makeSkill({ tools: ['exec', 'read_file'] })
    const instance = new SkillRegistry().register(skill, '/p')
    const sandbox = createSkillSandbox(instance)

    expect(sandbox.isToolAllowed('exec')).toBe(true)
    expect(sandbox.isToolAllowed('read_file')).toBe(true)
    expect(sandbox.isToolAllowed('browser')).toBe(false)
  })

  it('allows all tools when tools list is empty', () => {
    const skill = makeSkill({ tools: [] })
    const instance = new SkillRegistry().register(skill, '/p')
    const sandbox = createSkillSandbox(instance)

    expect(sandbox.isToolAllowed('anything')).toBe(true)
  })
})

// ─── evaluateSkillTrigger ────────────────────────────────────────

describe('evaluateSkillTrigger', () => {
  it('activates on keyword match', () => {
    const skill = makeSkill({ triggers: [{ event: 'agent:before_turn', keywords: ['help', 'assist'] }] })
    const result = evaluateSkillTrigger(skill, 'agent:before_turn', 'I need help with something')
    expect(result.shouldActivate).toBe(true)
    expect(result.confidence).toBeGreaterThanOrEqual(0.3)
  })

  it('activates on pattern match', () => {
    const skill = makeSkill({ triggers: [{ event: 'agent:before_turn', pattern: 'code.*review|review.*code' }] })
    const result = evaluateSkillTrigger(skill, 'agent:before_turn', 'please review my code')
    expect(result.shouldActivate).toBe(true)
  })

  it('returns low confidence on no match', () => {
    const skill = makeSkill({ triggers: [{ event: 'agent:before_turn', keywords: ['help'] }] })
    const result = evaluateSkillTrigger(skill, 'agent:before_turn', 'nothing relevant here')
    expect(result.shouldActivate).toBe(false)
  })

  it('activates on event-only triggers', () => {
    const skill = makeSkill({ triggers: [{ event: 'session:before_create' }] })
    const result = evaluateSkillTrigger(skill, 'session:before_create', '')
    expect(result.shouldActivate).toBe(true)
    expect(result.confidence).toBe(1.0)
  })

  it('returns inactive on wrong event', () => {
    const skill = makeSkill({ triggers: [{ event: 'startup:after' }] })
    const result = evaluateSkillTrigger(skill, 'agent:before_turn', '')
    expect(result.shouldActivate).toBe(false)
  })
})

// ─── validateSkillTools ──────────────────────────────────────────

describe('validateSkillTools', () => {
  it('returns no missing when all tools present', () => {
    const skill = makeSkill({ tools: ['exec', 'read_file'] })
    const instance = new SkillRegistry().register(skill, '/p')
    const missing = validateSkillTools(instance, ['exec', 'read_file', 'write_file'])
    expect(missing).toHaveLength(0)
  })

  it('returns missing tools', () => {
    const skill = makeSkill({ tools: ['exec', 'browser'] })
    const instance = new SkillRegistry().register(skill, '/p')
    const missing = validateSkillTools(instance, ['exec'])
    expect(missing).toEqual(['browser'])
  })
})

// ─── buildSkillPrompt ────────────────────────────────────────────

describe('buildSkillPrompt', () => {
  it('builds prompt from skill manifest', () => {
    const skill = makeSkill({ prompt: 'You are a code reviewer.', tools: ['exec', 'read_file'] })
    const instance = new SkillRegistry().register(skill, '/p')
    const prompt = buildSkillPrompt(instance)
    expect(prompt).toContain('You are a code reviewer.')
    expect(prompt).toContain('exec')
    expect(prompt).toContain('read_file')
  })

  it('returns empty for no prompt or tools', () => {
    const skill = makeSkill({ prompt: '', tools: [] })
    const instance = new SkillRegistry().register(skill, '/p')
    expect(buildSkillPrompt(instance)).toBe('')
  })
})

// ─── SkillsEngine ────────────────────────────────────────────────

describe('SkillsEngine', () => {
  let engine: SkillsEngine
  const skillsDir = join(testDir, 'engine-skills')

  beforeEach(() => {
    rmSync(skillsDir, { recursive: true, force: true })
    mkdirSync(skillsDir, { recursive: true })
    engine = new SkillsEngine({ skillsDir, autoActivateOnStartup: false })
  })

  it('initializes and creates skills dir', async () => {
    await engine.initialize()
    expect(existsSync(skillsDir)).toBe(true)
  })

  it('loads skills on init', async () => {
    mkdirSync(join(skillsDir, 'test-skill'), { recursive: true })
    writeFileSync(join(skillsDir, 'test-skill', 'manifest.json'), JSON.stringify({
      name: 'loaded-skill', version: '1.0.0',
    }))

    await engine.initialize()
    expect(engine.registry.count()).toBe(1)
    expect(engine.registry.get('loaded-skill')).toBeDefined()
  })

  it('activates and deactivates skills', async () => {
    engine.registry.register(makeSkill(), '/tmp')

    const active = await engine.activateSkill('test-skill')
    expect(active.state).toBe('active')

    const deactivated = await engine.deactivateSkill('test-skill')
    expect(deactivated.state).toBe('inactive')
  })

  it('throws on activating unknown skill', async () => {
    await expect(engine.activateSkill('unknown')).rejects.toThrow('not found')
  })

  it('returns active set with injections', async () => {
    const skill = makeSkill({ name: 'coder', prompt: 'You are a coder.', priority: 10, triggers: [{ event: 'agent:before_turn' }] })
    engine.registry.register(skill, '/tmp')
    await engine.activateSkill('coder')

    const activeSet = engine.getActiveSet()
    expect(activeSet.active).toHaveLength(1)
    expect(activeSet.injections).toHaveLength(1)
    expect(activeSet.injections[0]!.name).toBe('coder')
    expect(activeSet.injections[0]!.content).toContain('coder')
    expect(activeSet.injections[0]!.priority).toBe(10)
  })

  it('evaluates triggers and activates matching skills', async () => {
    const triggerSkill = makeSkill({
      name: 'helper',
      triggers: [{ event: 'agent:before_turn', keywords: ['help'] }],
      prompt: 'You are helpful.',
    })
    engine.registry.register(triggerSkill, '/tmp')

    const result = await engine.evaluateAndActivate('agent:before_turn', 'I need help')
    expect(result.active.some(s => s.manifest.name === 'helper')).toBe(true)
  })

  it('enforces max active skills', async () => {
    engine = new SkillsEngine({
      skillsDir,
      autoActivateOnStartup: false,
      maxActiveSkills: 2,
      conflictResolution: 'error',
    })

    engine.registry.register(makeSkill({ name: 's1', priority: 5 }), '/tmp')
    engine.registry.register(makeSkill({ name: 's2', priority: 10 }), '/tmp')
    engine.registry.register(makeSkill({ name: 's3', priority: 15 }), '/tmp')

    await engine.activateSkill('s1')
    await engine.activateSkill('s2')
    await expect(engine.activateSkill('s3')).rejects.toThrow('Max active skills')
  })

  it('displaces lowest priority skill when conflict resolution is priority', async () => {
    engine = new SkillsEngine({
      skillsDir,
      autoActivateOnStartup: false,
      maxActiveSkills: 2,
      conflictResolution: 'priority',
    })

    engine.registry.register(makeSkill({ name: 'low', priority: 1 }), '/tmp')
    engine.registry.register(makeSkill({ name: 'high', priority: 100 }), '/tmp')
    engine.registry.register(makeSkill({ name: 'mid', priority: 50 }), '/tmp')

    await engine.activateSkill('low')
    await engine.activateSkill('mid')

    await engine.activateSkill('high')

    expect(engine.registry.get('high')!.state).toBe('active')
    expect(engine.registry.get('low')!.state).toBe('inactive')
  })

  it('reloads a skill', async () => {
    mkdirSync(join(skillsDir, 'reloadable'), { recursive: true })
    writeFileSync(join(skillsDir, 'reloadable', 'manifest.json'), JSON.stringify({
      name: 'reloadable', version: '1.0.0',
    }))

    await engine.initialize()

    writeFileSync(join(skillsDir, 'reloadable', 'manifest.json'), JSON.stringify({
      name: 'reloadable', version: '2.0.0',
    }))

    const reloaded = await engine.reloadSkill('reloadable')
    expect(reloaded).not.toBeNull()
    expect(reloaded!.manifest.version).toBe('2.0.0')
  })

  it('disables a skill', async () => {
    engine.registry.register(makeSkill(), '/tmp')
    await engine.activateSkill('test-skill')
    await engine.disableSkill('test-skill')

    expect(engine.registry.get('test-skill')!.state).toBe('disabled')
  })

  it('returns metrics', async () => {
    engine.registry.register(makeSkill({ name: 'a' }), '/tmp')
    engine.registry.register(makeSkill({ name: 'b' }), '/tmp')
    await engine.activateSkill('a')

    const m = engine.getMetrics()
    expect(m.total).toBe(2)
    expect(m.active).toBe(1)
    expect(m.inactive).toBe(1)
  })

  it('validates required tools', () => {
    engine.registry.register(makeSkill({ name: 'needy', tools: ['exec', 'missing-tool'] }), '/tmp')
    const result = engine.validateRequiredTools(['exec', 'read_file'])
    expect(result.has('needy')).toBe(true)
    expect(result.get('needy')).toEqual(['missing-tool'])
  })
})
