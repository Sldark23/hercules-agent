export type JobStatus = 'active' | 'paused' | 'completed' | 'error'

export type Weekday = 0 | 1 | 2 | 3 | 4 | 5 | 6
export type Month = 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 | 11 | 12

export interface CronSchedule {
  minute: string
  hour: string
  dayOfMonth: string
  month: string
  dayOfWeek: string
}

export interface CronJob {
  id: string
  name: string
  schedule: CronSchedule
  input: string
  timezone: string
  status: JobStatus
  createdAt: Date
  updatedAt: Date
  lastRunAt?: Date
  lastResult?: string
  lastError?: string
  runCount: number
  maxRuns?: number
  expiresAt?: Date
  tags?: string[]
}

export interface JobExecution {
  id: string
  jobId: string
  startedAt: Date
  finishedAt?: Date
  durationMs?: number
  result?: string
  error?: string
  outputLines?: number
  success: boolean
}

export interface CronSchedulerConfig {
  dbPath: string
  pollIntervalMs: number
  defaultTimezone: string
  maxConcurrentJobs: number
  executionTimeoutMs: number
}

export interface SchedulerStats {
  totalJobs: number
  activeJobs: number
  pausedJobs: number
  totalExecutions: number
  lastPollTime?: Date
  isRunning: boolean
}
