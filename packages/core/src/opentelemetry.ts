export interface TelemetrySpan {
  name: string
  startTime: bigint
  endTime?: bigint
  attributes: Record<string, string>
  status?: 'ok' | 'error'
  children: TelemetrySpan[]
}

export interface TelemetryEvent {
  name: string
  timestamp: bigint
  attributes: Record<string, string>
}

export interface TelemetryMetric {
  name: string
  value: number
  unit: string
  timestamp: bigint
  attributes: Record<string, string>
}

export class SimpleTelemetry {
  private spans: TelemetrySpan[] = []
  private events: TelemetryEvent[] = []
  private metrics: TelemetryMetric[] = []
  private activeSpan: TelemetrySpan | null = null
  private enabled: boolean

  constructor(enabled = true) {
    this.enabled = enabled
  }

  startSpan(name: string, attributes: Record<string, string> = {}): { end: (status?: 'ok' | 'error') => void } {
    if (!this.enabled) return { end: () => {} }

    const span: TelemetrySpan = {
      name,
      startTime: process.hrtime.bigint(),
      attributes,
      children: [],
    }

    if (this.activeSpan) {
      this.activeSpan.children.push(span)
    } else {
      this.spans.push(span)
    }

    const parent = this.activeSpan
    this.activeSpan = span

    return {
      end: (status?: 'ok' | 'error') => {
        span.endTime = process.hrtime.bigint()
        span.status = status ?? 'ok'
        this.activeSpan = parent
      },
    }
  }

  recordEvent(name: string, attributes: Record<string, string> = {}): void {
    if (!this.enabled) return
    this.events.push({
      name,
      timestamp: process.hrtime.bigint(),
      attributes,
    })
  }

  recordMetric(name: string, value: number, unit: string = '1', attributes: Record<string, string> = {}): void {
    if (!this.enabled) return
    this.metrics.push({
      name,
      value,
      unit,
      timestamp: process.hrtime.bigint(),
      attributes,
    })
  }

  getSpans(): TelemetrySpan[] {
    return this.spans
  }

  getEvents(): TelemetryEvent[] {
    return this.events
  }

  getMetrics(): TelemetryMetric[] {
    return this.metrics
  }

  getDurationMs(span: TelemetrySpan): number {
    if (!span.endTime) return 0
    return Number(span.endTime - span.startTime) / 1_000_000
  }

  export(): { spans: TelemetrySpan[]; events: TelemetryEvent[]; metrics: TelemetryMetric[] } {
    return {
      spans: this.spans,
      events: this.events,
      metrics: this.metrics,
    }
  }

  reset(): void {
    this.spans = []
    this.events = []
    this.metrics = []
    this.activeSpan = null
  }
}

export function createAgentTelemetry(id: string) {
  const telemetry = new SimpleTelemetry()
  return {
    telemetry,
    instrumented: {
      async measure<T>(name: string, fn: () => Promise<T>, attrs: Record<string, string> = {}): Promise<T> {
        const span = telemetry.startSpan(name, { agentId: id, ...attrs })
        try {
          const result = await fn()
          span.end('ok')
          return result
        } catch (err) {
          span.end('error')
          telemetry.recordEvent('error', { name, error: (err as Error).message })
          throw err
        }
      },
    },
    flush: () => telemetry.reset(),
  }
}
