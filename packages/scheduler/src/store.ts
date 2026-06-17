import { readFile, writeFile, mkdir } from 'node:fs/promises'
import { existsSync } from 'node:fs'
import { dirname } from 'node:path'
import { randomUUID } from 'node:crypto'
import type { CronJob, JobExecution, JobStatus } from './types.js'

export interface JobStoreConfig {
  dbPath: string
}

export class JobStore {
  private config: JobStoreConfig
  private jobs: Map<string, CronJob> = new Map()
  private executions: Map<string, JobExecution[]> = new Map()
  private initialized = false

  constructor(config: JobStoreConfig) {
    this.config = config
  }

  async init(): Promise<void> {
    if (this.initialized) return

    const dir = dirname(this.config.dbPath)
    if (!existsSync(dir)) {
      await mkdir(dir, { recursive: true })
    }

    if (existsSync(this.config.dbPath)) {
      try {
        const raw = await readFile(this.config.dbPath, 'utf-8')
        const data = JSON.parse(raw)

        if (data.jobs) {
          for (const [id, job] of Object.entries(data.jobs)) {
            this.jobs.set(id, reviveDates(job as Record<string, unknown>) as CronJob)
          }
        }
        if (data.executions) {
          for (const [id, execs] of Object.entries(data.executions)) {
            this.executions.set(id, (execs as Record<string, unknown>[]).map(e => reviveDates(e) as JobExecution))
          }
        }
      } catch {}
    }

    this.initialized = true
  }

  async save(): Promise<void> {
    const dir = dirname(this.config.dbPath)
    if (!existsSync(dir)) {
      await mkdir(dir, { recursive: true })
    }

    const data = {
      jobs: Object.fromEntries(this.jobs),
      executions: Object.fromEntries(this.executions),
    }
    await writeFile(this.config.dbPath, JSON.stringify(data, null, 2), 'utf-8')
  }

  // ─── Jobs ──────────────────────────────────────────────────────

  createJob(job: Omit<CronJob, 'id' | 'createdAt' | 'updatedAt' | 'runCount' | 'status'>): CronJob {
    const id = randomUUID()
    const newJob: CronJob = {
      id,
      name: job.name,
      schedule: job.schedule,
      input: job.input,
      timezone: job.timezone,
      status: 'active',
      createdAt: new Date(),
      updatedAt: new Date(),
      runCount: 0,
      maxRuns: job.maxRuns,
      expiresAt: job.expiresAt,
      tags: job.tags,
    }

    this.jobs.set(id, newJob)
    return newJob
  }

  getJob(id: string): CronJob | undefined {
    return this.jobs.get(id)
  }

  listJobs(filter?: { status?: JobStatus; tag?: string }): CronJob[] {
    let results = Array.from(this.jobs.values())

    if (filter?.status) {
      results = results.filter(j => j.status === filter.status)
    }
    if (filter?.tag) {
      results = results.filter(j => j.tags?.includes(filter.tag!))
    }

    return results.sort((a, b) => a.createdAt.getTime() - b.createdAt.getTime())
  }

  updateJob(id: string, updates: Partial<CronJob>): CronJob {
    const job = this.jobs.get(id)
    if (!job) throw new Error(`Job "${id}" not found`)

    Object.assign(job, updates, { updatedAt: new Date() })
    return job
  }

  deleteJob(id: string): boolean {
    const deleted = this.jobs.delete(id)
    this.executions.delete(id)
    return deleted
  }

  // ─── Executions ────────────────────────────────────────────────

  createExecution(jobId: string): JobExecution {
    const exec: JobExecution = {
      id: randomUUID(),
      jobId,
      startedAt: new Date(),
      success: false,
    }

    const existing = this.executions.get(jobId) ?? []
    existing.push(exec)
    this.executions.set(jobId, existing)

    return exec
  }

  finishExecution(executionId: string, jobId: string, result: {
    success: boolean
    result?: string
    error?: string
    outputLines?: number
  }): JobExecution {
    const execs = this.executions.get(jobId)
    if (!execs) throw new Error(`No executions found for job "${jobId}"`)

    const exec = execs.find(e => e.id === executionId)
    if (!exec) throw new Error(`Execution "${executionId}" not found for job "${jobId}"`)

    exec.finishedAt = new Date()
    exec.durationMs = exec.finishedAt.getTime() - exec.startedAt.getTime()
    exec.result = result.result
    exec.error = result.error
    exec.outputLines = result.outputLines
    exec.success = result.success

    return exec
  }

  listExecutions(jobId: string, limit = 20): JobExecution[] {
    const execs = this.executions.get(jobId) ?? []
    return execs.slice(-limit)
  }

  countExecutions(): number {
    let total = 0
    for (const execs of this.executions.values()) {
      total += execs.length
    }
    return total
  }

  // ─── Maintenance ───────────────────────────────────────────────

  getDueJobs(now: Date): CronJob[] {
    return this.listJobs({ status: 'active' }).filter(job => {
      if (job.expiresAt && job.expiresAt < now) return false
      if (job.maxRuns && job.runCount >= job.maxRuns) return false
      return true
    })
  }

  incrementRunCount(id: string): void {
    const job = this.jobs.get(id)
    if (job) {
      job.runCount++
      job.lastRunAt = new Date()
      if (job.maxRuns && job.runCount >= job.maxRuns) {
        job.status = 'completed'
      }
    }
  }

  cleanupOldExecutions(jobId: string, maxAgeDays = 30): number {
    const execs = this.executions.get(jobId)
    if (!execs) return 0

    const cutoff = Date.now() - maxAgeDays * 86400000
    const before = execs.length
    this.executions.set(jobId, execs.filter(e => e.startedAt.getTime() > cutoff))
    return before - (this.executions.get(jobId)?.length ?? 0)
  }
}

function reviveDates(obj: Record<string, unknown>): Record<string, unknown> {
  const dateFields = ['createdAt', 'updatedAt', 'lastRunAt', 'startedAt', 'finishedAt', 'expiresAt']
  for (const key of dateFields) {
    if (typeof obj[key] === 'string') {
      obj[key] = new Date(obj[key] as string)
    }
  }
  return obj
}
