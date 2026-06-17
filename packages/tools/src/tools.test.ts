import { describe, it, expect, beforeEach, afterEach } from 'vitest'
import { ToolRegistry } from './registry.js'
import { createExecTool, executeCommand } from './exec-tool.js'
import { createFileTools, withPathGuard } from './file-tools.js'
import { AnthropicParser, OpenAIParser, DeepSeekParser, QwenParser, LlamaParser, getParser } from './parsers/model-parsers.js'
import { randomUUID } from 'node:crypto'
import { writeFile, mkdir } from 'node:fs/promises'
import { join } from 'node:path'
import { tmpdir } from 'node:os'

// ─── ToolRegistry ──────────────────────────────────────────────────

describe('ToolRegistry', () => {
  let registry: ToolRegistry

  beforeEach(() => {
    registry = new ToolRegistry()
  })

  it('registers and retrieves tools', () => {
    registry.register({
      name: 'echo', description: 'Echo input',
      inputSchema: { safeParse: () => ({ success: true, data: {} }) } as any,
      handler: async () => ({ toolCallId: '', output: '' }),
    })
    expect(registry.get('echo')).toBeDefined()
    expect(registry.has('echo')).toBe(true)
  })

  it('throws on duplicate registration', () => {
    registry.register({
      name: 'dup', description: '', inputSchema: { safeParse: () => ({ success: true, data: {} }) } as any,
      handler: async () => ({ toolCallId: '', output: '' }),
    })
    expect(() => registry.register({
      name: 'dup', description: '', inputSchema: { safeParse: () => ({ success: true, data: {} }) } as any,
      handler: async () => ({ toolCallId: '', output: '' }),
    })).toThrow('already registered')
  })

  it('lists tools by category', () => {
    registry.registerBatch([
      { name: 'a', description: '', inputSchema: {} as any, handler: async () => ({ toolCallId: '', output: '' }), category: 'system' },
      { name: 'b', description: '', inputSchema: {} as any, handler: async () => ({ toolCallId: '', output: '' }), category: 'filesystem' },
    ])
    expect(registry.list('system')).toHaveLength(1)
    expect(registry.list('filesystem')).toHaveLength(1)
  })

  it('supports aliases', () => {
    registry.register({
      name: 'original', description: '', inputSchema: {} as any,
      handler: async () => ({ toolCallId: '', output: '' }),
    })
    registry.alias('short', 'original')
    expect(registry.get('short')?.name).toBe('original')
  })

  it('converts to ToolDefinition array', () => {
    registry.register({
      name: 'test', description: 'desc', inputSchema: {} as any,
      handler: async () => ({ toolCallId: '', output: '' }),
    })
    const defs = registry.toToolDefinitions()
    expect(defs).toHaveLength(1)
    expect(defs[0]!.name).toBe('test')
  })

  it('validates input against schema', () => {
    const { z } = require('zod')
    registry.register({
      name: 'validated', description: '', inputSchema: z.object({ x: z.number() }),
      handler: async () => ({ toolCallId: '', output: '' }),
    })
    expect(registry.validate('validated', { x: 1 }).success).toBe(true)
    expect(registry.validate('validated', { x: 'not-a-number' }).success).toBe(false)
  })
})

// ─── withPathGuard ─────────────────────────────────────────────────

describe('withPathGuard', () => {
  const root = '/workspace'
  const { guard } = withPathGuard(root)

  it('allows paths within workspace', () => {
    expect(guard('file.txt')).toBe('/workspace/file.txt')
    expect(guard('sub/dir/file.ts')).toBe('/workspace/sub/dir/file.ts')
  })

  it('blocks path traversal attacks', () => {
    expect(() => guard('../etc/passwd')).toThrow('Path traversal denied')
    expect(() => guard('../../etc/passwd')).toThrow('Path traversal denied')
  })

  it('resolves absolute paths within workspace', () => {
    expect(guard('/workspace/foo/bar.ts')).toBe('/workspace/foo/bar.ts')
  })
})

// ─── Model Parsers ─────────────────────────────────────────────────

describe('AnthropicParser', () => {
  const parser = new AnthropicParser()

  it('parses function_calls XML', () => {
    const result = parser.parse(`<function_calls>
<invoke name="read_file">
{"path": "test.txt"}
</invoke>
</function_calls>`)
    expect(result).toHaveLength(1)
    expect(result![0]!.name).toBe('read_file')
  })

  it('returns null when no calls', () => {
    expect(parser.parse('Just a normal response.')).toBeNull()
  })
})

describe('OpenAIParser', () => {
  const parser = new OpenAIParser()

  it('parses TOOL_CALL format', () => {
    const result = parser.parse(`[TOOL_CALL] read_file
{"path": "test.txt"}`)
    expect(result).toHaveLength(1)
    expect(result![0]!.name).toBe('read_file')
  })

  it('parses JSON code block format', () => {
    const result = parser.parse('Some text\n```json\n[{"type":"function","function":{"name":"search","arguments":{"q":"hello"}}}]\n```')
    expect(result).toHaveLength(1)
    expect(result![0]!.name).toBe('search')
  })
})

describe('DeepSeekParser', () => {
  const parser = new DeepSeekParser()

  it('parses tool_call XML', () => {
    const result = parser.parse(`<tool_call>
{"name": "read_file", "arguments": {"path": "test.txt"}}
</tool_call>`)
    expect(result).toHaveLength(1)
    expect(result![0]!.name).toBe('read_file')
  })
})

describe('QwenParser', () => {
  const parser = new QwenParser()

  it('parses Qwen tool_call format', () => {
    const result = parser.parse(`<tool_call>{"name": "get_weather", "arguments": {"city": "Tokyo"}}</tool_call>`)
    expect(result).toHaveLength(1)
    expect(result![0]!.name).toBe('get_weather')
  })
})

describe('LlamaParser', () => {
  const parser = new LlamaParser()

  it('parses Llama function format', () => {
    const result = parser.parse(JSON.stringify({ function: { name: 'search', parameters: { q: 'test' } } }))
    expect(result).toHaveLength(1)
    expect(result![0]!.name).toBe('search')
  })
})

describe('getParser', () => {
  it('returns correct parser per model', () => {
    expect(getParser('claude-3-5-sonnet')).toBeInstanceOf(AnthropicParser)
    expect(getParser('deepseek-v3')).toBeInstanceOf(DeepSeekParser)
    expect(getParser('qwen-2.5')).toBeInstanceOf(QwenParser)
    expect(getParser('llama-3')).toBeInstanceOf(LlamaParser)
    expect(getParser('gpt-4o')).toBeInstanceOf(OpenAIParser)
  })
})

// ─── File Tools ────────────────────────────────────────────────────

describe('File Tools (integration)', () => {
  const testDir = join(tmpdir(), `hercules-test-${randomUUID().slice(0, 8)}`)
  let tools: ReturnType<typeof createFileTools>

  beforeEach(async () => {
    await mkdir(testDir, { recursive: true })
    tools = createFileTools(testDir)
  })

  it('write and read files', async () => {
    const writeTool = tools.find(t => t.name === 'write_file')!
    const readTool = tools.find(t => t.name === 'read_file')!

    await writeTool.handler({ path: 'hello.txt', content: 'world' }, { sessionId: '', workspaceDir: testDir, env: {} })
    const readResult = await readTool.handler({ path: 'hello.txt' }, { sessionId: '', workspaceDir: testDir, env: {} })

    expect(readResult.output).toBe('world')
  })

  it('blocks path traversal', async () => {
    const readTool = tools.find(t => t.name === 'read_file')!
    const result = await readTool.handler({ path: '../../etc/passwd' }, { sessionId: '', workspaceDir: testDir, env: {} })
    expect(result.isError).toBe(true)
    expect(result.output).toContain('Path traversal denied')
  })
})
