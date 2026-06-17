import { describe, it, expect, vi } from 'vitest'
import { withRetry, calculateDelay, MessageQueue, createRetryableFetch } from './retry.js'

describe('calculateDelay', () => {
  it('exponential backoff', () => {
    expect(calculateDelay(0)).toBe(1000)
    expect(calculateDelay(1)).toBe(2000)
    expect(calculateDelay(2)).toBe(4000)
  })

  it('respects max delay', () => {
    const large = calculateDelay(10, { baseDelayMs: 10000, maxDelayMs: 15000, maxRetries: 10, backoffFactor: 2, retryableStatuses: [] })
    expect(large).toBe(15000)
  })
})

describe('withRetry', () => {
  it('succeeds on first attempt', async () => {
    const fn = vi.fn().mockResolvedValue('ok')
    expect(await withRetry(fn)).toBe('ok')
    expect(fn).toHaveBeenCalledTimes(1)
  })

  it('retries on failure', async () => {
    const fn = vi.fn()
      .mockRejectedValueOnce(new Error('fail 1'))
      .mockRejectedValueOnce(new Error('fail 2'))
      .mockResolvedValueOnce('ok')

    expect(await withRetry(fn, { baseDelayMs: 10, maxDelayMs: 50 })).toBe('ok')
    expect(fn).toHaveBeenCalledTimes(3)
  })

  it('throws after max retries', async () => {
    const fn = vi.fn().mockRejectedValue(new Error('always fail'))
    await expect(withRetry(fn, { baseDelayMs: 10, maxDelayMs: 50, maxRetries: 2 }))
      .rejects.toThrow('always fail')
    expect(fn).toHaveBeenCalledTimes(3)
  })
})

describe('MessageQueue', () => {
  it('processes items sequentially', async () => {
    const q = new MessageQueue()
    const order: number[] = []

    const p1 = q.enqueue(async () => { order.push(1); return 'a' })
    const p2 = q.enqueue(async () => { order.push(2); return 'b' })

    expect(await p1).toBe('a')
    expect(await p2).toBe('b')
    expect(order).toEqual([1, 2])
  })

  it('tracks queue length', () => {
    const q = new MessageQueue()
    expect(q.length).toBe(0)
  })
})
