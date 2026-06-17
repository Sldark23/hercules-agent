import { z } from 'zod'
import { spawn, execSync, type ChildProcess } from 'node:child_process'
import { writeFile, unlink, mkdtemp } from 'node:fs/promises'
import { join } from 'node:path'
import { tmpdir } from 'node:os'
import type { RegisteredTool } from './registry.js'

export const ExecInput = z.object({
  command: z.string().min(1, 'Command is required'),
  args: z.array(z.string()).optional(),
  cwd: z.string().optional(),
  env: z.record(z.string(), z.string()).optional(),
  timeout: z.number().positive().max(300_000).optional().default(30_000),
  backend: z.enum(['local', 'docker', 'ssh']).optional().default('local'),
  dockerImage: z.string().optional(),
  sshHost: z.string().optional(),
  captureOutput: z.boolean().optional().default(true),
})

export type ExecInput = z.infer<typeof ExecInput>
export interface ExecResult { stdout: string; stderr: string; exitCode: number; durationMs: number }

interface ExecBackend {
  execute(input: ExecInput, ctx: { sessionId: string; workspaceDir: string }): Promise<ExecResult>
}

class LocalBackend implements ExecBackend {
  async execute(input: ExecInput): Promise<ExecResult> {
    const start = Date.now()

    return new Promise((resolve, reject) => {
      const proc: ChildProcess = spawn(input.command, input.args ?? [], {
        cwd: input.cwd,
        env: { ...process.env, ...input.env },
        stdio: input.captureOutput ? ['pipe', 'pipe', 'pipe'] : 'inherit',
        shell: true,
      })

      let stdout = ''
      let stderr = ''
      let timedOut = false

      const timer = setTimeout(() => {
        timedOut = true
        proc.kill('SIGTERM')
      }, input.timeout)

      if (proc.stdout) proc.stdout.on('data', (d: Buffer) => { stdout += d.toString() })
      if (proc.stderr) proc.stderr.on('data', (d: Buffer) => { stderr += d.toString() })

      proc.on('close', (code) => {
        clearTimeout(timer)
        if (timedOut) {
          reject(new Error(`Command timed out after ${input.timeout}ms`))
        } else {
          resolve({ stdout, stderr, exitCode: code ?? -1, durationMs: Date.now() - start })
        }
      })
      proc.on('error', (err) => { clearTimeout(timer); reject(err) })
    })
  }
}

class DockerBackend implements ExecBackend {
  async execute(input: ExecInput, ctx: { workspaceDir: string }): Promise<ExecResult> {
    const image = input.dockerImage ?? 'ubuntu:22.04'
    const scriptPath = join(ctx.workspaceDir, `.hercules-exec-${Date.now()}.sh`)
    const script = `#!/bin/sh\n${input.command} ${(input.args ?? []).join(' ')}\n`

    await writeFile(scriptPath, script, { mode: 0o755 })
    const start = Date.now()

    try {
      const cmd = `docker run --rm -v "${ctx.workspaceDir}:/workspace" -w /workspace ${image} /bin/sh /workspace/${scriptPath.replace(ctx.workspaceDir, '').replace(/^\//, '')}`
      const stdout = execSync(cmd, {
        timeout: input.timeout,
        cwd: input.cwd ?? ctx.workspaceDir,
        env: { ...process.env, ...input.env },
        encoding: 'utf-8',
        stdio: input.captureOutput ? 'pipe' : 'inherit',
      })
      return { stdout: stdout?.toString() ?? '', stderr: '', exitCode: 0, durationMs: Date.now() - start }
    } catch (err: unknown) {
      const error = err as { stdout?: string; stderr?: string; status?: number }
      return {
        stdout: (error.stdout ?? '').toString(),
        stderr: (error.stderr ?? '').toString(),
        exitCode: error.status ?? 1,
        durationMs: Date.now() - start,
      }
    } finally {
      await unlink(scriptPath).catch(() => {})
    }
  }
}

class SSHBackend implements ExecBackend {
  async execute(input: ExecInput): Promise<ExecResult> {
    if (!input.sshHost) throw new Error('sshHost is required for SSH backend')
    const sshCmd = `ssh ${input.sshHost} ${input.command} ${(input.args ?? []).join(' ')}`
    const start = Date.now()

    try {
      const stdout = execSync(sshCmd, {
        timeout: input.timeout,
        encoding: 'utf-8',
        stdio: 'pipe',
      })
      return { stdout: stdout?.toString() ?? '', stderr: '', exitCode: 0, durationMs: Date.now() - start }
    } catch (err: unknown) {
      const error = err as { stdout?: string; stderr?: string; status?: number }
      return {
        stdout: (error.stdout ?? '').toString(),
        stderr: (error.stderr ?? '').toString(),
        exitCode: error.status ?? 1,
        durationMs: Date.now() - start,
      }
    }
  }
}

const backends: Record<string, ExecBackend> = {
  local: new LocalBackend(),
  docker: new DockerBackend(),
  ssh: new SSHBackend(),
}

export async function executeCommand(
  input: ExecInput,
  ctx: { sessionId: string; workspaceDir: string }
): Promise<ExecResult> {
  const backend = backends[input.backend]
  if (!backend) throw new Error(`Unknown backend: "${input.backend}"`)
  return backend.execute(input, ctx)
}

export function createExecTool(): RegisteredTool {
  return {
    name: 'exec',
    description: 'Execute a shell command locally, in Docker, or over SSH. Returns stdout, stderr, and exit code.',
    inputSchema: ExecInput,
    category: 'system',
    requiresApproval: true,
    handler: async (input, ctx) => {
      const result = await executeCommand(input as ExecInput, ctx)
      return {
        toolCallId: '',
        output: result.exitCode === 0
          ? result.stdout
          : `Exit code ${result.exitCode}\nstdout: ${result.stdout}\nstderr: ${result.stderr}`,
        isError: result.exitCode !== 0,
        metadata: { durationMs: result.durationMs, exitCode: result.exitCode },
      }
    },
  }
}
