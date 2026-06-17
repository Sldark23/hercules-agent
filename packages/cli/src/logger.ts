type LogLevel = 'debug' | 'info' | 'warn' | 'error' | 'silent'

const LEVEL_NUM: Record<LogLevel, number> = {
  debug: 0, info: 1, warn: 2, error: 3, silent: 4,
}

const PREFIX: Record<LogLevel, string> = {
  debug: '[hercules:debug]',
  info: '[hercules]',
  warn: '[hercules:warn]',
  error: '[hercules:error]',
  silent: '',
}

function getLevel(): LogLevel {
  const env = process.env.HERCULES_LOG_LEVEL ?? 'info'
  if (env in LEVEL_NUM) return env as LogLevel
  return 'info'
}

const currentLevel = getLevel()

function shouldLog(level: LogLevel): boolean {
  return LEVEL_NUM[level] >= LEVEL_NUM[currentLevel]
}

function formatMeta(meta?: Record<string, unknown>): string {
  if (!meta || Object.keys(meta).length === 0) return ''
  if (process.env.HERCULES_LOG_JSON) {
    return ' ' + JSON.stringify(meta)
  }
  return ' ' + Object.entries(meta)
    .map(([k, v]) => `${k}=${v}`)
    .join(' ')
}

export const logger = {
  debug(msg: string, meta?: Record<string, unknown>): void {
    if (!shouldLog('debug')) return
    console.error(`${PREFIX.debug} ${msg}${formatMeta(meta)}`)
  },

  info(msg: string, meta?: Record<string, unknown>): void {
    if (!shouldLog('info')) return
    console.error(`${PREFIX.info} ${msg}${formatMeta(meta)}`)
  },

  warn(msg: string, meta?: Record<string, unknown>): void {
    if (!shouldLog('warn')) return
    console.error(`${PREFIX.warn} ${msg}${formatMeta(meta)}`)
  },

  error(msg: string, meta?: Record<string, unknown>): void {
    if (!shouldLog('error')) return
    console.error(`${PREFIX.error} ${msg}${formatMeta(meta)}`)
  },

  stdout(msg: string): void {
    console.log(msg)
  },
}
