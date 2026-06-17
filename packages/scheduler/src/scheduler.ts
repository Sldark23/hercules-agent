import { JobStore } from './store.js'
import { parseCronExpression, matchesSchedule } from './cron-parser.js'
import type { CronJob, JobExecution, CronSchedulerConfig, SchedulerStats } from './types.js'

export type JobHandler = (job: CronJob) => Promise<string>

export class CronScheduler {
  private config: CronSchedulerConfig
  readonly store: JobStore
  private handler?: JobHandler
  private timer: ReturnType<typeof setInterval> | null = null
  private running = false
  private runningJobs = new Set<string>()
  private lastPollTime?: Date

  constructor(config: Partial<CronSchedulerConfig> = {}) {
    this.config = {
      dbPath: config.dbPath ?? './data/scheduler.json',
      pollIntervalMs: config.pollIntervalMs ?? 60_000,
      defaultTimezone: config.defaultTimezone ?? 'UTC',
      maxConcurrentJobs: config.maxConcurrentJobs ?? 10,
      executionTimeoutMs: config.executionTimeoutMs ?? 300_000,
    }

    this.store = new JobStore({ dbPath: this.config.dbPath })
  }

  async initialize(handler: JobHandler): Promise<void> {
    await this.store.init()
    this.handler = handler
  }

  onJob(handler: JobHandler): void {
    this.handler = handler
  }

  start(): void {
    if (this.running) return
    this.running = true

    this.timer = setInterval(async () => {
      await this.poll()
    }, this.config.pollIntervalMs)

    this.poll()
  }

  stop(): void {
    this.running = false
    if (this.timer) {
      clearInterval(this.timer)
      this.timer = null
    }
  }

  isRunning(): boolean {
    return this.running
  }

  // ─── Job Management ────────────────────────────────────────────

  schedule(options: {
    name: string
    expression: string
    input: string
    timezone?: string
    maxRuns?: number
    expiresAt?: Date
    tags?: string[]
  }): CronJob {
    const schedule = parseCronExpression(options.expression)

    return this.store.createJob({
      name: options.name,
      schedule,
      input: options.input,
      timezone: options.timezone ?? this.config.defaultTimezone,
      maxRuns: options.maxRuns,
      expiresAt: options.expiresAt,
      tags: options.tags,
    })
  }

  async unschedule(jobId: string): Promise<boolean> {
    const job = this.store.getJob(jobId)
    if (!job) return false

    this.store.deleteJob(jobId)
    await this.store.save()
    return true
  }

  async pause(jobId: string): Promise<CronJob> {
    const job = this.store.updateJob(jobId, { status: 'paused' })
    await this.store.save()
    return job
  }

  async resume(jobId: string): Promise<CronJob> {
    const job = this.store.updateJob(jobId, { status: 'active' })
    await this.store.save()
    return job
  }

  // ─── Polling ───────────────────────────────────────────────────

  async poll(): Promise<void> {
    if (!this.handler) return

    const now = new Date()
    this.lastPollTime = now

    const activeJobs = this.store.getDueJobs(now)

    for (const job of activeJobs) {
      if (this.runningJobs.size >= this.config.maxConcurrentJobs) break
      if (this.runningJobs.has(job.id)) continue

      const matches = matchesSchedule(job.schedule, now)

      if (matches) {
        this.executeJob(job)
      }
    }
  }

  private async executeJob(job: CronJob): Promise<void> {
    if (!this.handler) return

    this.runningJobs.add(job.id)
    const exec = this.store.createExecution(job.id)
    this.store.incrementRunCount(job.id)

    try {
      const timeout = new Promise<never>((_, reject) =>
        setTimeout(() => reject(new Error(`Job "${job.name}" timed out after ${this.config.executionTimeoutMs}ms`)), this.config.executionTimeoutMs)
      )

      const result = await Promise.race([
        this.handler(job),
        timeout,
      ])

      this.store.finishExecution(exec.id, job.id, {
        success: true,
        result,
        outputLines: result.split('\n').length,
      })

      this.store.updateJob(job.id, {
        lastResult: result,
        lastError: undefined,
      })
    } catch (err) {
      const errMsg = (err as Error).message
      this.store.finishExecution(exec.id, job.id, {
        success: false,
        error: errMsg,
      })

      this.store.updateJob(job.id, {
        lastError: errMsg,
        status: 'error',
      })
    } finally {
      this.runningJobs.delete(job.id)
      await this.store.save()
    }
  }

  // ─── Query ─────────────────────────────────────────────────────

  getJob(id: string): CronJob | undefined {
    return this.store.getJob(id)
  }

  listJobs(filter?: { status?: string; tag?: string }): CronJob[] {
    return this.store.listJobs(filter as any)
  }

  getExecutions(jobId: string, limit?: number): JobExecution[] {
    return this.store.listExecutions(jobId, limit)
  }

  getStats(): SchedulerStats {
    const all = this.store.listJobs()
    return {
      totalJobs: all.length,
      activeJobs: all.filter(j => j.status === 'active').length,
      pausedJobs: all.filter(j => j.status === 'paused').length,
      totalExecutions: this.store.countExecutions(),
      lastPollTime: this.lastPollTime,
      isRunning: this.running,
    }
  }

  async close(): Promise<void> {
    this.stop()
    await this.store.save()
  }
}
