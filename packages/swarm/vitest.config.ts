import { defineConfig } from 'vitest/config'
import { resolve } from 'node:path'

export default defineConfig({
  resolve: {
    alias: {
      '@hercules/core': resolve('../../packages/core/src/index.ts'),
      '@hercules/tools': resolve('../../packages/tools/src/index.ts'),
      '@hercules/plugins': resolve('../../packages/plugins/src/index.ts'),
      '@hercules/cli': resolve('../../packages/cli/src/index.ts'),
      '@hercules/security': resolve('../../packages/security/src/index.ts'),
      '@hercules/gateway': resolve('../../packages/gateway/src/index.ts'),
      '@hercules/channels': resolve('../../packages/channels/src/index.ts'),
      '@hercules/memory': resolve('../../packages/memory/src/index.ts'),
      '@hercules/skills': resolve('../../packages/skills/src/index.ts'),
      '@hercules/scheduler': resolve('../../packages/scheduler/src/index.ts'),
    },
  },
  test: {
    include: ['src/**/*.test.ts'],
    globals: true,
    environment: 'node',
  },
})
