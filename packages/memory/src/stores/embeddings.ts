export interface EmbeddingProvider {
  embed(text: string): Promise<number[]>
  embedBatch(texts: string[]): Promise<number[][]>
  dimensions: number
}

export class OpenAIEmbeddingProvider implements EmbeddingProvider {
  readonly dimensions = 1536
  private apiKey: string
  private model: string

  constructor(opts: { apiKey?: string; model?: string } = {}) {
    this.apiKey = opts.apiKey ?? process.env.OPENAI_API_KEY ?? ''
    this.model = opts.model ?? 'text-embedding-3-small'
  }

  isConfigured(): boolean {
    return !!this.apiKey
  }

  async embed(text: string): Promise<number[]> {
    const [vec] = await this.embedBatch([text])
    return vec
  }

  async embedBatch(texts: string[]): Promise<number[][]> {
    const cleanedTexts = texts.map(t => t.replace(/\n/g, ' ').slice(0, 8000))

    const res = await fetch('https://api.openai.com/v1/embeddings', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${this.apiKey}`,
      },
      body: JSON.stringify({
        input: cleanedTexts,
        model: this.model,
      }),
    })

    if (!res.ok) {
      throw new Error(`OpenAI embedding API error: ${res.status} ${await res.text()}`)
    }

    const data = (await res.json()) as {
      data: Array<{ index: number; embedding: number[] }>
    }

    return data.data.sort((a, b) => a.index - b.index).map(d => d.embedding)
  }
}

export class LocalEmbeddingProvider implements EmbeddingProvider {
  readonly dimensions = 384

  async embed(text: string): Promise<number[]> {
    return this.fakeEmbedding(text)
  }

  async embedBatch(texts: string[]): Promise<number[][]> {
    return texts.map(t => this.fakeEmbedding(t))
  }

  private fakeEmbedding(text: string): number[] {
    const dim = this.dimensions
    const vec: number[] = new Array(dim)
    let hash = 0
    for (let i = 0; i < text.length; i++) {
      hash = ((hash << 5) - hash) + text.charCodeAt(i)
      hash |= 0
    }
    for (let i = 0; i < dim; i++) {
      vec[i] = Math.sin(hash * (i + 1)) * 0.5 + 0.5
    }
    return vec
  }
}

export function createEmbeddingProvider(): EmbeddingProvider {
  const openai = new OpenAIEmbeddingProvider()
  if (openai.isConfigured()) return openai
  return new LocalEmbeddingProvider()
}
