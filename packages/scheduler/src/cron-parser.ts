import type { CronSchedule } from './types.js'

export function parseCronExpression(expr: string): CronSchedule {
  const parts = expr.trim().split(/\s+/)

  if (parts.length < 5) {
    throw new Error(`Invalid cron expression "${expr}": expected 5 fields (minute hour day month weekday), got ${parts.length}`)
  }

  if (parts.length > 5) {
    throw new Error(`Invalid cron expression "${expr}": expected 5 fields, got ${parts.length}. Use 5-field standard (no seconds field)`)
  }

  validateField(parts[0]!, 0, 59, 'minute')
  validateField(parts[1]!, 0, 23, 'hour')
  validateField(parts[2]!, 1, 31, 'day of month')
  validateField(parts[3]!, 1, 12, 'month')
  validateField(parts[4]!, 0, 6, 'day of week')

  return {
    minute: parts[0]!,
    hour: parts[1]!,
    dayOfMonth: parts[2]!,
    month: parts[3]!,
    dayOfWeek: parts[4]!,
  }
}

function validateField(field: string, min: number, max: number, name: string): void {
  if (field === '*') return

  const segments = field.split(',')

  for (const segment of segments) {
    if (segment.includes('-')) {
      const parts = segment.split('-').map(s => parseInt(s.trim(), 10))
      const start = parts[0]
      const end = parts[1]
      if (start === undefined || end === undefined || isNaN(start) || isNaN(end)) throw new Error(`Invalid range in cron ${name} field "${field}"`)
      if (start < min || end > max) throw new Error(`Range [${start}-${end}] out of bounds for ${name} field (${min}-${max})`)
    } else if (segment.includes('/')) {
      const parts = segment.split('/')
      const base = parts[0]
      const step = parts[1]
      if (base === undefined) throw new Error(`Invalid step in cron ${name} field "${field}"`)
      validateField(base, min, max, name)
      if (step === undefined || isNaN(parseInt(step, 10))) throw new Error(`Invalid step in cron ${name} field "${field}"`)
    } else {
      const num = parseInt(segment, 10)
      if (isNaN(num)) throw new Error(`Invalid cron ${name} field "${field}"`)
      if (num < min || num > max) throw new Error(`Value ${num} out of range for ${name} field (${min}-${max})`)
    }
  }
}

export function matchesSchedule(schedule: CronSchedule, date: Date): boolean {
  if (!fieldMatches(schedule.minute, date.getMinutes())) return false
  if (!fieldMatches(schedule.hour, date.getHours())) return false
  if (!fieldMatches(schedule.dayOfMonth, date.getDate())) return false
  if (!fieldMatches(schedule.month, date.getMonth() + 1)) return false
  if (!fieldMatches(schedule.dayOfWeek, date.getDay())) return false

  return true
}

function fieldMatches(pattern: string, value: number): boolean {
  if (pattern === '*') return true

  const segments = pattern.split(',')

  for (const segment of segments) {
    if (segment.includes('/')) {
      const parts = segment.split('/')
      const base = parts[0]
      const stepStr = parts[1]
      const step = parseInt(stepStr ?? '', 10)
      if (isNaN(step)) continue
      const baseVal = base === '*' || base === undefined ? 0 : (rangesMatch(base, value) ? value : -1)
      if (baseVal < 0) continue
      if ((value - baseVal) % step === 0) return true
    } else if (rangesMatch(segment, value)) {
      return true
    }
  }

  return false
}

function rangesMatch(pattern: string, value: number): boolean {
  if (!pattern.includes('-')) {
    return parseInt(pattern, 10) === value
  }

  const [startStr, endStr] = pattern.split('-')
  const start = parseInt(startStr!, 10)
  const end = parseInt(endStr!, 10)

  if (isNaN(start) || isNaN(end)) return false
  return value >= start && value <= end
}

export function humanReadableCron(schedule: CronSchedule): string {
  const joined = `${schedule.minute} ${schedule.hour} ${schedule.dayOfMonth} ${schedule.month} ${schedule.dayOfWeek}`

  if (joined === '* * * * *') return 'Every minute'
  if (schedule.minute !== '*' && schedule.hour === '*' && schedule.dayOfMonth === '*' && schedule.month === '*' && schedule.dayOfWeek === '*') {
    return `At minute ${schedule.minute} of every hour`
  }
  if (schedule.minute === '0' && schedule.hour !== '*' && schedule.dayOfMonth === '*' && schedule.month === '*' && schedule.dayOfWeek === '*') {
    return `Daily at ${schedule.hour.padStart(2, '0')}:00`
  }
  if (schedule.minute === '0' && schedule.hour === '9' && schedule.dayOfMonth === '*' && schedule.month === '*' && schedule.dayOfWeek === '*') {
    return 'Daily at 09:00'
  }

  return joined
}

export function nextRunDate(schedule: CronSchedule, from: Date = new Date()): Date {
  const candidate = new Date(from)

  for (let i = 0; i < 525600; i++) {
    candidate.setMinutes(candidate.getMinutes() + 1)
    if (matchesSchedule(schedule, candidate)) return candidate
  }

  throw new Error('No future date found within 1 year for cron schedule')
}
