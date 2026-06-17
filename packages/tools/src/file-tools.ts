import { z } from 'zod'
import { readFile, writeFile, readdir, unlink, stat, mkdir, appendFile, copyFile, rename } from 'node:fs/promises'
import { join, resolve, normalize, relative } from 'node:path'
import { existsSync } from 'node:fs'
import type { RegisteredTool } from './registry.js'

export const ReadInput = z.object({
  path: z.string().min(1),
  encoding: z.enum(['utf-8', 'base64', 'hex']).optional().default('utf-8'),
  offset: z.number().min(0).optional(),
  limit: z.number().min(1).optional(),
})

export const WriteInput = z.object({
  path: z.string().min(1),
  content: z.string(),
  encoding: z.enum(['utf-8', 'base64', 'hex']).optional().default('utf-8'),
  append: z.boolean().optional().default(false),
})

export const ListInput = z.object({
  path: z.string().min(1),
  pattern: z.string().optional(),
  recursive: z.boolean().optional().default(false),
})

export const SearchInput = z.object({
  path: z.string().min(1),
  pattern: z.string().min(1),
  glob: z.string().optional(),
})

export const DeleteInput = z.object({
  path: z.string().min(1),
  recursive: z.boolean().optional().default(false),
})

export const MoveInput = z.object({
  source: z.string().min(1),
  destination: z.string().min(1),
})

export function withPathGuard(root: string) {
  function guard(target: string): string {
    const resolved = resolve(root, target)
    const normalized = normalize(resolved)
    const rootNormalized = normalize(resolve(root))

    if (!normalized.startsWith(rootNormalized)) {
      throw new Error(`Path traversal denied: "${target}" resolves outside workspace`)
    }
    return normalized
  }

  return { guard }
}

export function createFileTools(workspaceRoot: string): RegisteredTool[] {
  const { guard } = withPathGuard(workspaceRoot)

  const readTool: RegisteredTool = {
    name: 'read_file',
    description: 'Read a file from the workspace. Returns content as string.',
    inputSchema: ReadInput,
    category: 'filesystem',
    handler: async (input) => {
      const { path, encoding, offset, limit } = input as z.infer<typeof ReadInput>
      let fullPath: string
      try { fullPath = guard(path) }
      catch (e) { return { toolCallId: '', output: (e as Error).message, isError: true } }
      if (!existsSync(fullPath)) return { toolCallId: '', output: `File not found: ${path}`, isError: true }

      const enc = encoding as BufferEncoding
      const buffer = await readFile(fullPath)
      let content = enc === 'utf-8' ? buffer.toString('utf-8') : buffer.toString(enc)

      if (limit !== undefined) {
        const lines = content.split('\n')
        content = lines.slice(offset ?? 0, (offset ?? 0) + limit).join('\n')
      } else if (offset !== undefined) {
        const lines = content.split('\n')
        content = lines.slice(offset).join('\n')
      }

      if (content.length > 100_000) {
        content = content.slice(0, 100_000) + `\n\n... [truncated at 100K chars]`
      }

      return { toolCallId: '', output: content }
    },
  }

  const writeTool: RegisteredTool = {
    name: 'write_file',
    description: 'Write content to a file in the workspace. Creates parent directories if needed.',
    inputSchema: WriteInput,
    category: 'filesystem',
    handler: async (input) => {
      const { path, content, encoding, append } = input as z.infer<typeof WriteInput>
      let fullPath: string
      try { fullPath = guard(path) }
      catch (e) { return { toolCallId: '', output: (e as Error).message, isError: true } }
      await mkdir(fullPath.split('/').slice(0, -1).join('/'), { recursive: true }).catch(() => {})

      if (append) {
        await appendFile(fullPath, content, encoding as BufferEncoding)
      } else {
        await writeFile(fullPath, content, encoding as BufferEncoding)
      }
      const size = (await stat(fullPath)).size
      return { toolCallId: '', output: `Written ${size} bytes to ${path}` }
    },
  }

  const listTool: RegisteredTool = {
    name: 'list_files',
    description: 'List files and directories in the workspace.',
    inputSchema: ListInput,
    category: 'filesystem',
    handler: async (input) => {
      const { path, recursive } = input as z.infer<typeof ListInput>
      let fullPath: string
      try { fullPath = guard(path) }
      catch (e) { return { toolCallId: '', output: (e as Error).message, isError: true } }
      if (!existsSync(fullPath)) return { toolCallId: '', output: `Path not found: ${path}`, isError: true }

      const entries = await readdir(fullPath, { withFileTypes: true, recursive })
      const lines = entries.map(e => {
        const rel = relative(fullPath, join(fullPath, e.name))
        return e.isDirectory() ? `${rel}/` : rel
      })
      return { toolCallId: '', output: lines.sort().join('\n') || '(empty directory)' }
    },
  }

  const deleteTool: RegisteredTool = {
    name: 'delete_file',
    description: 'Delete a file or directory from the workspace.',
    inputSchema: DeleteInput,
    category: 'filesystem',
    handler: async (input) => {
      const { path, recursive } = input as z.infer<typeof DeleteInput>
      let fullPath: string
      try { fullPath = guard(path) }
      catch (e) { return { toolCallId: '', output: (e as Error).message, isError: true } }
      if (!existsSync(fullPath)) return { toolCallId: '', output: `Not found: ${path}`, isError: true }

      const s = await stat(fullPath)
      if (s.isDirectory() && !recursive) {
        return { toolCallId: '', output: 'Is a directory. Use recursive: true to delete.', isError: true }
      }
      await unlink(fullPath)
      return { toolCallId: '', output: `Deleted: ${path}` }
    },
  }

  const moveTool: RegisteredTool = {
    name: 'move_file',
    description: 'Move or rename a file or directory.',
    inputSchema: MoveInput,
    category: 'filesystem',
    handler: async (input) => {
      const { source, destination } = input as z.infer<typeof MoveInput>
      let srcFull: string, dstFull: string
      try { srcFull = guard(source); dstFull = guard(destination) }
      catch (e) { return { toolCallId: '', output: (e as Error).message, isError: true } }
      await mkdir(dstFull.split('/').slice(0, -1).join('/'), { recursive: true }).catch(() => {})
      await rename(srcFull, dstFull)
      return { toolCallId: '', output: `Moved ${source} → ${destination}` }
    },
  }

  const searchTool: RegisteredTool = {
    name: 'search_files',
    description: 'Search for files by name pattern (glob) or content regex.',
    inputSchema: SearchInput,
    category: 'filesystem',
    handler: async (input) => {
      const { path, pattern, glob } = input as z.infer<typeof SearchInput>
      let fullPath: string
      try { fullPath = guard(path) }
      catch (e) { return { toolCallId: '', output: (e as Error).message, isError: true } }

      let cmd: string
      if (glob) {
        cmd = `find "${fullPath}" -type f -name "${glob}" 2>/dev/null`
      } else {
        cmd = `rg -l "${pattern}" "${fullPath}" 2>/dev/null || echo ""`
      }

      const { execSync } = await import('node:child_process')
      const result = execSync(cmd, { encoding: 'utf-8', timeout: 10_000 }).toString().trim()

      return { toolCallId: '', output: result || 'No matches found' }
    },
  }

  return [readTool, writeTool, listTool, deleteTool, moveTool, searchTool]
}
