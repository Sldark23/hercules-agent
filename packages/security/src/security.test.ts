import { describe, it, expect, beforeEach, afterEach } from 'vitest'
import { GuardrailEngine } from './guardrails.js'
import { RateLimiter } from './rate-limiter.js'
import { PermissionManager } from './permissions.js'
import { InputSanitizer } from './sanitizer.js'

describe('GuardrailEngine', () => {
  let engine: GuardrailEngine

  beforeEach(() => { engine = new GuardrailEngine() })

  it('allows safe input', async () => {
    const result = await engine.check('echo hello world')
    expect(result.action).toBe('allow')
  })

  it('blocks rm -rf /', async () => {
    const result = await engine.check('rm -rf /')
    expect(result.action).toBe('block')
    expect(result.severity).toBe('critical')
  })

  it('blocks fork bomb', async () => {
    const result = await engine.check(':() { :|:& };:')
    expect(result.action).toBe('block')
  })

  it('flags API keys', async () => {
    const result = await engine.check('sk-proj-abcdefghijklmnopqrstuvwxyz123456')
    expect(result.action === 'flag' || result.action === 'sanitize').toBe(true)
  })

  it('sanitizes sensitive data', async () => {
    const result = await engine.check('my key is sk-proj-abcdefghijklmnopqrstuvwxyz123456')
    if (result.sanitizedContent) {
      expect(result.sanitizedContent).not.toContain('sk-proj-')
    }
  })

  it('blocks after max flags', async () => {
    await engine.check('key sk-proj-abcdefghijklmnopqrstuvwxyz123456', { userId: 'u1' })
    await engine.check('key sk-proj-abcdefghijklmnopqrstuvwxyz123456', { userId: 'u1' })
    const result = await engine.check('key sk-proj-abcdefghijklmnopqrstuvwxyz123456', { userId: 'u1' })
    expect(result.action).toBe('block')
  })

  it('supports monitoring mode', async () => {
    engine.setMode('monitoring')
    const result = await engine.check('rm -rf /')
    expect(result.action).not.toBe('block')
  })

  it('adds and removes rules', () => {
    engine.addRule({
      name: 'custom-block', description: 'Custom rule', severity: 'high',
      pattern: /evil/i, action: 'block',
    })
    expect(engine.getRules().length).toBeGreaterThan(0)
    expect(engine.removeRule('custom-block')).toBe(true)
  })
})

describe('RateLimiter', () => {
  let limiter: RateLimiter

  beforeEach(() => {
    limiter = new RateLimiter()
    limiter.defineLimit('api', { windowMs: 60000, maxRequests: 3, type: 'ip' })
  })

  afterEach(() => { limiter.destroy() })

  it('allows requests within limit', () => {
    expect(limiter.check('api', '127.0.0.1').allowed).toBe(true)
    expect(limiter.check('api', '127.0.0.1').allowed).toBe(true)
    expect(limiter.check('api', '127.0.0.1').allowed).toBe(true)
  })

  it('blocks requests exceeding limit', () => {
    for (let i = 0; i < 3; i++) limiter.check('api', '127.0.0.1')
    const result = limiter.check('api', '127.0.0.1')
    expect(result.allowed).toBe(false)
    expect(result.remaining).toBe(0)
  })

  it('allows different keys independently', () => {
    for (let i = 0; i < 3; i++) limiter.check('api', 'ip-a')
    expect(limiter.check('api', 'ip-b').allowed).toBe(true)
  })

  it('returns remaining count', () => {
    limiter.check('api', 'key-1')
    const result = limiter.check('api', 'key-1')
    expect(result.allowed).toBe(true)
    expect(result.remaining).toBe(1)
  })
})

describe('PermissionManager', () => {
  let pm: PermissionManager

  beforeEach(() => { pm = new PermissionManager() })

  it('allows admin all access', () => {
    expect(pm.checkPermission('admin', { resource: 'filesystem', action: 'write' })).toBe(true)
    expect(pm.checkPermission('admin', { resource: 'network', action: 'execute' })).toBe(true)
  })

  it('allows developer filesystem access', () => {
    expect(pm.checkPermission('developer', { resource: 'filesystem', action: 'read' })).toBe(true)
    expect(pm.checkPermission('developer', { resource: 'filesystem', action: 'write' })).toBe(true)
  })

  it('denies developer exec write', () => {
    expect(pm.checkPermission('developer', { resource: 'exec', action: 'write' })).toBe(false)
  })

  it('denies user exec access', () => {
    expect(pm.checkPermission('user', { resource: 'exec', action: 'read' })).toBe(false)
  })

  it('manages approval requests', () => {
    const req = pm.requestApproval({
      toolName: 'exec',
      arguments: { command: 'rm -rf' },
      sessionId: 's1',
      reason: 'Need to execute command',
    })
    expect(req.status).toBe('pending')

    pm.approveApproval(req.id, 'admin')
    expect(pm.getApproval(req.id)?.status).toBe('approved')
  })

  it('lists pending approvals', () => {
    pm.requestApproval({ toolName: 'exec', arguments: {}, sessionId: 's1', reason: 'test' })
    expect(pm.getPendingApprovals()).toHaveLength(1)
  })
})

describe('InputSanitizer', () => {
  let sanitizer: InputSanitizer

  beforeEach(() => { sanitizer = new InputSanitizer() })

  it('allows safe env vars', () => {
    expect(sanitizer.sanitizeEnvVar('HOME')).toBe('HOME')
    expect(sanitizer.sanitizeEnvVar('PATH')).toBe('PATH')
  })

  it('blocks dangerous env vars', () => {
    expect(sanitizer.sanitizeEnvVar('LD_PRELOAD')).toBeNull()
    expect(sanitizer.sanitizeEnvVar('SHELLCODE')).toBeNull()
  })

  it('sanitizes path traversal', () => {
    expect(sanitizer.sanitizePath('../../etc/passwd')).toBe('etc/passwd')
  })

  it('sanitizes command injection', () => {
    expect(sanitizer.sanitizeCommand('$(cat /etc/passwd)')).toContain('[BLOCKED_SUBSHELL]')
    expect(sanitizer.sanitizeCommand('`cat /etc/passwd`')).toContain('[BLOCKED_SUBSHELL]')
  })

  it('redacts secrets', () => {
    const result = sanitizer.redactSecrets('ghp_abcdefghijklmnopqrstuvwxyz1234567890')
    expect(result).toContain('[REDACTED]')
  })

  it('sanitizes JSON with secrets', () => {
    const result = sanitizer.sanitizeJsonInput({ apiKey: 'sk-xxx', name: 'test' })
    expect((result as Record<string, unknown>).apiKey).toBe('[REDACTED]')
    expect((result as Record<string, unknown>).name).toBe('test')
  })
})
