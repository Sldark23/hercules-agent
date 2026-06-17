import { ModelRouter, CredentialPool, ContextEngine } from '@hercules/core'
import { ToolRegistry, createExecTool, createFileTools, createBrowserTool, createMcpTool } from '@hercules/tools'
import { readFile, access } from 'node:fs/promises'
import { join } from 'node:path'
import { homedir } from 'node:os'

const ENV_VAR_TO_PROVIDER: Record<string, string> = {
  OPENAI_API_KEY: 'openai',
  ANTHROPIC_API_KEY: 'anthropic',
  GOOGLE_API_KEY: 'google',
  MISTRAL_API_KEY: 'mistral',
  DEEPSEEK_API_KEY: 'deepseek',
  GROQ_API_KEY: 'groq',
  XAI_API_KEY: 'xai',
  COHERE_API_KEY: 'cohere',
  TOGETHER_API_KEY: 'together',
  PERPLEXITY_API_KEY: 'perplexity',
  FIREWORKS_API_KEY: 'fireworks',
  REPLICATE_API_KEY: 'replicate',
  HUGGINGFACE_API_KEY: 'huggingface',
  ANYSCALE_API_KEY: 'anyscale',
  GITHUB_API_KEY: 'github',
  AI21_API_KEY: 'ai21',
  OCTOAI_API_KEY: 'octoai',
  LEPTON_API_KEY: 'lepton',
  DEEPINFRA_API_KEY: 'deepinfra',
  NOVITA_API_KEY: 'novita',
  LAMBDATEST_API_KEY: 'lambdatest',
  AZURE_API_KEY: 'azure',
}

async function loadApiKeys(): Promise<Record<string, string>> {
  const keys: Record<string, string> = {}

  for (const [envVar, provider] of Object.entries(ENV_VAR_TO_PROVIDER)) {
    const val = process.env[envVar]
    if (val) keys[provider] = val
  }

  try {
    const envPath = join(homedir(), '.hercules', '.env')
    await access(envPath)
    const content = await readFile(envPath, 'utf-8')
    for (const line of content.split('\n')) {
      const trimmed = line.trim()
      if (!trimmed || trimmed.startsWith('#')) continue
      const eqIdx = trimmed.indexOf('=')
      if (eqIdx === -1) continue
      const key = trimmed.slice(0, eqIdx).trim() as keyof typeof ENV_VAR_TO_PROVIDER
      const value = trimmed.slice(eqIdx + 1).trim()
      const provider = ENV_VAR_TO_PROVIDER[key]
      if (provider && value && !keys[provider]) {
        keys[provider] = value
      }
    }
  } catch {}

  return keys
}

export interface BootstrapResult {
  modelRouter: ModelRouter
  context: ContextEngine
  toolRegistry: ToolRegistry
  toolDefinitions: ReturnType<ToolRegistry['toToolDefinitions']>
  apiKeys: Record<string, string>
}

export async function createBootstrap(opts: {
  defaultModel?: string
  sessionId: string
  workspaceDir?: string
}): Promise<BootstrapResult> {
  const apiKeys = await loadApiKeys()

  const routerConfig: ConstructorParameters<typeof ModelRouter>[1] = {
    defaultModel: opts.defaultModel ?? 'gpt-4o',
    maxRetries: 3,
    autoDiscover: true,
  }

  const credentialPool = new CredentialPool()
  const modelRouter = new ModelRouter(credentialPool, routerConfig)

  await modelRouter.autoConfigure(apiKeys)

  const context = new ContextEngine({ maxTokens: 200_000 })
  context.init(opts.sessionId)

  const toolRegistry = new ToolRegistry()
  toolRegistry.register(createExecTool())
  toolRegistry.registerBatch(createFileTools(opts.workspaceDir ?? process.cwd()))
  toolRegistry.register(createBrowserTool())
  toolRegistry.register(createMcpTool())

  return {
    modelRouter,
    context,
    toolRegistry,
    toolDefinitions: toolRegistry.toToolDefinitions(),
    apiKeys,
  }
}
