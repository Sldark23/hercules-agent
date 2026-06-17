import { z } from 'zod'

export const PluginManifestSchema = z.object({
  name: z.string().min(1),
  version: z.string().regex(/^\d+\.\d+\.\d+$/),
  description: z.string().default(''),
  author: z.string().optional(),
  license: z.string().optional(),
  entry: z.string().default('index.js'),
  type: z.enum(['tool', 'channel', 'provider', 'memory', 'hook', 'skill', 'extension']).default('extension'),
  dependencies: z.record(z.string(), z.string()).optional(),
  requires: z.array(z.string()).optional(),
  permissions: z.array(z.enum([
    'filesystem:read', 'filesystem:write',
    'network:http', 'network:ws',
    'exec:local', 'exec:docker',
    'env:read',
  ])).optional(),
  config: z.record(z.unknown()).optional(),
  hooks: z.array(z.string()).optional(),
})

export type PluginManifest = z.infer<typeof PluginManifestSchema>

export type PluginType = PluginManifest['type']

export type PluginState = 'registered' | 'loading' | 'loaded' | 'activating' | 'active' | 'error' | 'disabled'

export interface PluginInstance {
  id: string
  manifest: PluginManifest
  state: PluginState
  path: string
  exports: Record<string, unknown>
  hooks: Record<string, Function[]>
  error?: string
  loadedAt?: Date
}

export interface PluginMetadata {
  id: string
  name: string
  version: string
  description: string
  author?: string
  type: PluginType
  downloads?: number
  rating?: number
  source?: 'registry' | 'local' | 'bundled'
  repository?: string
  homepage?: string
}
