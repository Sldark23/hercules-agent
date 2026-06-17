export interface RetryConfig {
  maxRetries: number
  baseDelayMs: number
  maxDelayMs: number
  backoffFactor: number
  retryableStatuses: number[]
}

const DEFAULT_CONFIG: RetryConfig = {
  maxRetries: 3,
  baseDelayMs: 1000,
  maxDelayMs: 30_000,
  backoffFactor: 2,
  retryableStatuses: [429, 500, 502, 503, 504],
}

export function calculateDelay(attempt: number, config: RetryConfig = DEFAULT_CONFIG): number {
  const delay = config.baseDelayMs * Math.pow(config.backoffFactor, attempt)
  return Math.min(delay, config.maxDelayMs)
}

export async function withRetry<T>(
  fn: () => Promise<T>,
  config: Partial<RetryConfig> = {},
  context?: string
): Promise<T> {
  const cfg = { ...DEFAULT_CONFIG, ...config }
  let lastError: Error | undefined

  for (let attempt = 0; attempt <= cfg.maxRetries; attempt++) {
    try {
      return await fn()
    } catch (err) {
      lastError = err instanceof Error ? err : new Error(String(err))

      const status = (err as { status?: number })?.status
      if (status && !cfg.retryableStatuses.includes(status)) {
        throw err
      }

      if (attempt === cfg.maxRetries) {
        const ctx = context ? ` [${context}]` : ''
        throw new Error(`Failed after ${cfg.maxRetries} retries${ctx}: ${lastError.message}`)
      }

      const delay = calculateDelay(attempt, cfg)
      await new Promise(r => setTimeout(r, delay))
    }
  }

  throw lastError ?? new Error('Unexpected retry error')
}

export function createRetryableFetch(config?: Partial<RetryConfig>) {
  const cfg = { ...DEFAULT_CONFIG, ...config }

  return async (url: string, options?: RequestInit): Promise<Response> => {
    return withRetry(async () => {
      const res = await fetch(url, options)
      if (!res.ok) {
        const err = new Error(`HTTP ${res.status}: ${res.statusText}`) as Error & { status: number }
        err.status = res.status
        throw err
      }
      return res
    }, cfg, url)
  }
}

export class MessageQueue {
  private queue: Array<{ fn: () => Promise<unknown>; resolve: (v: unknown) => void; reject: (e: Error) => void }> = []
  private processing = false

  async enqueue<T>(fn: () => Promise<T>): Promise<T> {
    return new Promise<T>((resolve, reject) => {
      this.queue.push({ fn, resolve: resolve as (v: unknown) => void, reject })
      this.process()
    })
  }

  private async process(): Promise<void> {
    if (this.processing) return
    this.processing = true

    while (this.queue.length > 0) {
      const item = this.queue.shift()!
      try {
        const result = await item.fn()
        item.resolve(result)
      } catch (err) {
        item.reject(err instanceof Error ? err : new Error(String(err)))
      }
    }

    this.processing = false
  }

  get length(): number {
    return this.queue.length
  }
}
