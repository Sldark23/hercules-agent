import { describe, it, expect, beforeEach, afterEach } from 'vitest'
import { mkdtempSync, writeFileSync, mkdirSync, rmSync, existsSync } from 'node:fs'
import { join } from 'node:path'
import { tmpdir } from 'node:os'
import { CronScheduler } from './scheduler.js'
import { JobStore } from './store.js'
import { parseCronExpression, matchesSchedule, nextRunDate, humanReadableCron } from './cron-parser.js'
import type { CronSchedule, CronJob } from './types.js'

const testDir = mkdtempSync(join(tmpdir(), 'scheduler-test-'))

// ─── Cron Parser ─────────────────────────────────────────────────

describe('parseCronExpression', () => {
  it('parses standard 5-field cron', () => {
    const s = parseCronExpression('0 9 * * 1-5')
    expect(s.minute).toBe('0')
    expect(s.hour).toBe('9')
    expect(s.dayOfMonth).toBe('*')
    expect(s.month).toBe('*')
    expect(s.dayOfWeek).toBe('1-5')
  })

  it('handles wildcard fields', () => {
    const s = parseCronExpression('* * * * *')
    expect(s.minute).toBe('*')
    expect(s.hour).toBe('*')
    expect(s.dayOfMonth).toBe('*')
    expect(s.month).toBe('*')
    expect(s.dayOfWeek).toBe('*')
  })

  it('parses comma-separated lists', () => {
    const s = parseCronExpression('0 9,18 * * 1,3,5')
    expect(s.hour).toBe('9,18')
    expect(s.dayOfWeek).toBe('1,3,5')
  })

  it('rejects too few fields', () => {
    expect(() => parseCronExpression('* * * *')).toThrow('expected 5 fields')
  })

  it('rejects too many fields (with seconds)', () => {
    expect(() => parseCronExpression('0 0 * * * *')).toThrow('expected 5 fields')
  })

  it('rejects out of range values', () => {
    expect(() => parseCronExpression('60 * * * *')).toThrow('out of range')
    expect(() => parseCronExpression('* 24 * * *')).toThrow('out of range')
    expect(() => parseCronExpression('* * 32 * *')).toThrow('out of range')
    expect(() => parseCronExpression('* * * 13 *')).toThrow('out of range')
    expect(() => parseCronExpression('* * * * 7')).toThrow('out of range')
  })
})

describe('matchesSchedule', () => {
  it('matches wildcard schedule', () => {
    const s: CronSchedule = { minute: '*', hour: '*', dayOfMonth: '*', month: '*', dayOfWeek: '*' }
    expect(matchesSchedule(s, new Date())).toBe(true)
  })

  it('matches exact time', () => {
    const d = new Date('2026-06-16T14:30:00')
    const s: CronSchedule = { minute: '30', hour: '14', dayOfMonth: '16', month: '6', dayOfWeek: '2' }
    expect(matchesSchedule(s, d)).toBe(true)
  })

  it('matches range expression', () => {
    const d = new Date('2026-06-17T14:30:00')
    const s: CronSchedule = { minute: '30', hour: '14', dayOfMonth: '*', month: '*', dayOfWeek: '1-5' }
    expect(matchesSchedule(s, d)).toBe(true)
  })

  it('rejects wrong minute', () => {
    const d = new Date('2026-06-16T14:31:00')
    const s: CronSchedule = { minute: '30', hour: '14', dayOfMonth: '16', month: '6', dayOfWeek: '2' }
    expect(matchesSchedule(s, d)).toBe(false)
  })

  it('rejects weekend when range is weekdays', () => {
    const saturday = new Date('2026-06-20T14:30:00')
    const s: CronSchedule = { minute: '30', hour: '14', dayOfMonth: '*', month: '*', dayOfWeek: '1-5' }
    expect(matchesSchedule(s, saturday)).toBe(false)
  })
})

describe('nextRunDate', () => {
  it('finds next minute for every-minute cron', () => {
    const s: CronSchedule = { minute: '*', hour: '*', dayOfMonth: '*', month: '*', dayOfWeek: '*' }
    const from = new Date('2026-06-16T14:30:00')
    const next = nextRunDate(s, from)
    expect(next.getTime()).toBeGreaterThan(from.getTime())
  })

  it('finds next occurrence for specific time', () => {
    const s: CronSchedule = { minute: '0', hour: '9', dayOfMonth: '*', month: '*', dayOfWeek: '*' }
    const from = new Date('2026-06-16T14:30:00')
    const next = nextRunDate(s, from)
    expect(next.getHours()).toBe(9)
    expect(next.getMinutes()).toBe(0)
    expect(next.getTime()).toBeGreaterThan(from.getTime())
  })
})

describe('humanReadableCron', () => {
  it('describes every minute', () => {
    expect(humanReadableCron({ minute: '*', hour: '*', dayOfMonth: '*', month: '*', dayOfWeek: '*' }))
      .toBe('Every minute')
  })

  it('describes daily at 09:00', () => {
    expect(humanReadableCron({ minute: '0', hour: '9', dayOfMonth: '*', month: '*', dayOfWeek: '*' }))
      .toBe('Daily at 09:00')
  })
})

// ─── JobStore ────────────────────────────────────────────────────

describe('JobStore', () => {
  let store: JobStore
  const dbPath = join(testDir, 'store', 'jobs.json')

  beforeEach(async () => {
    mkdirSync(join(testDir, 'store'), { recursive: true })
    store = new JobStore({ dbPath })
    await store.init()
  })

  afterEach(async () => {
    rmSync(join(testDir, 'store'), { recursive: true, force: true })
  })

  it('creates and retrieves jobs', () => {
    const job = store.createJob({
      name: 'test-job',
      schedule: { minute: '0', hour: '9', dayOfMonth: '*', month: '*', dayOfWeek: '*' },
      input: 'daily report',
      timezone: 'UTC',
    })

    expect(job.id).toBeDefined()
    expect(job.name).toBe('test-job')
    expect(job.status).toBe('active')

    const retrieved = store.getJob(job.id)
    expect(retrieved).toBeDefined()
    expect(retrieved!.name).toBe('test-job')
  })

  it('lists jobs with filters', () => {
    store.createJob({ name: 'j1', schedule: everyMinute(), input: 'a', timezone: 'UTC' })
    store.createJob({ name: 'j2', schedule: everyMinute(), input: 'b', timezone: 'UTC', tags: ['daily'] })
    store.createJob({ name: 'j3', schedule: everyMinute(), input: 'c', timezone: 'UTC', tags: ['daily'] })

    expect(store.listJobs()).toHaveLength(3)
    expect(store.listJobs({ tag: 'daily' })).toHaveLength(2)
  })

  it('updates jobs', () => {
    const job = store.createJob({ name: 'u1', schedule: everyMinute(), input: 'x', timezone: 'UTC' })
    store.updateJob(job.id, { status: 'paused' })
    expect(store.getJob(job.id)!.status).toBe('paused')
  })

  it('deletes jobs', () => {
    const job = store.createJob({ name: 'd1', schedule: everyMinute(), input: 'x', timezone: 'UTC' })
    expect(store.deleteJob(job.id)).toBe(true)
    expect(store.getJob(job.id)).toBeUndefined()
  })

  it('manages job executions', () => {
    const job = store.createJob({ name: 'e1', schedule: everyMinute(), input: 'x', timezone: 'UTC' })
    const exec = store.createExecution(job.id)
    expect(exec.success).toBe(false)

    store.finishExecution(exec.id, job.id, { success: true, result: 'done', outputLines: 1 })
    const finished = store.listExecutions(job.id)[0]!
    expect(finished.success).toBe(true)
    expect(finished.durationMs).toBeGreaterThanOrEqual(0)
  })

  it('persists and reloads', async () => {
    const job = store.createJob({ name: 'persist', schedule: everyMinute(), input: 'x', timezone: 'UTC' })
    const exec = store.createExecution(job.id)
    store.finishExecution(exec.id, job.id, { success: true, result: 'persisted' })
    await store.save()

    const store2 = new JobStore({ dbPath })
    await store2.init()

    expect(store2.getJob(job.id)).toBeDefined()
    expect(store2.listExecutions(job.id)).toHaveLength(1)
  })

  it('increments run count and auto-completes at maxRuns', () => {
    const job = store.createJob({
      name: 'maxed',
      schedule: everyMinute(),
      input: 'x',
      timezone: 'UTC',
      maxRuns: 2,
    })

    store.incrementRunCount(job.id)
    expect(store.getJob(job.id)!.runCount).toBe(1)
    expect(store.getJob(job.id)!.status).toBe('active')

    store.incrementRunCount(job.id)
    expect(store.getJob(job.id)!.runCount).toBe(2)
    expect(store.getJob(job.id)!.status).toBe('completed')
  })
})

// ─── CronScheduler ───────────────────────────────────────────────

describe('CronScheduler', () => {
  let scheduler: CronScheduler
  let executed: string[] = []
  const dbPath = join(testDir, 'scheduler', 'data.json')

  beforeEach(async () => {
    mkdirSync(join(testDir, 'scheduler'), { recursive: true })
    executed = []

    scheduler = new CronScheduler({
      dbPath,
      pollIntervalMs: 100,
      executionTimeoutMs: 5000,
      maxConcurrentJobs: 5,
    })

    const handler = async (job: CronJob) => {
      executed.push(job.name)
      return `executed ${job.name}`
    }

    await scheduler.initialize(handler)
  })

  afterEach(async () => {
    scheduler.stop()
    await scheduler.close()
    rmSync(join(testDir, 'scheduler'), { recursive: true, force: true })
  })

  it('schedules and manages jobs', () => {
    const job = scheduler.schedule({
      name: 'report',
      expression: '0 9 * * *',
      input: 'generate report',
      tags: ['daily'],
    })

    expect(job.name).toBe('report')
    expect(job.status).toBe('active')

    const listed = scheduler.listJobs()
    expect(listed).toHaveLength(1)
  })

  it('pauses and resumes jobs', async () => {
    const job = scheduler.schedule({ name: 'pausable', expression: '* * * * *', input: 'x' })
    await scheduler.pause(job.id)
    expect(scheduler.getJob(job.id)!.status).toBe('paused')

    await scheduler.resume(job.id)
    expect(scheduler.getJob(job.id)!.status).toBe('active')
  })

  it('unschedules jobs', async () => {
    const job = scheduler.schedule({ name: 'removable', expression: '* * * * *', input: 'x' })
    expect(await scheduler.unschedule(job.id)).toBe(true)
    expect(scheduler.getJob(job.id)).toBeUndefined()
  })

  it('starts and stops polling', () => {
    expect(scheduler.isRunning()).toBe(false)
    scheduler.start()
    expect(scheduler.isRunning()).toBe(true)
    scheduler.stop()
    expect(scheduler.isRunning()).toBe(false)
  })

  it('returns stats', () => {
    scheduler.schedule({ name: 's1', expression: '0 9 * * *', input: 'a' })
    scheduler.schedule({ name: 's2', expression: '0 9 * * *', input: 'b' })

    const stats = scheduler.getStats()
    expect(stats.totalJobs).toBe(2)
    expect(stats.activeJobs).toBe(2)
    expect(stats.isRunning).toBe(false)
  })

  it('tracks execution timeout', async () => {
    const timeoutScheduler = new CronScheduler({
      dbPath: join(testDir, 'scheduler', 'timeout.json'),
      executionTimeoutMs: 50,
    })

    const slowHandler = async () => {
      await new Promise(r => setTimeout(r, 500))
      return 'too late'
    }

    await timeoutScheduler.initialize(slowHandler)

    const job = timeoutScheduler.store.createJob({
      name: 'slow',
      schedule: everyMinute(),
      input: 'x',
      timezone: 'UTC',
    })

    await timeoutScheduler['executeJob'](job)
    expect(timeoutScheduler.getJob(job.id)!.lastError).toContain('timed out')
    expect(timeoutScheduler.getJob(job.id)!.status).toBe('error')

    await timeoutScheduler.close()
  })
})

function everyMinute(): CronSchedule {
  return { minute: '*', hour: '*', dayOfMonth: '*', month: '*', dayOfWeek: '*' }
}
