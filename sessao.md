# Sessão — 2026-06-17

## O que foi feito

### Casts frágeis corrigidos (discord.ts + whatsapp.ts)
- `event.data as string` → type check com fallback
- `pkt.op as number` → `Number()`, `pkt.s as number` → `typeof === 'number'`
- `author?.global_name as string` → `typeof === 'string'`
- Arrays do webhook validados com `Array.isArray()`
- `valueMeta?.display_phone_number` com acesso seguro

### Versionamento (Changesets)
- `@changesets/cli` + `@changesets/changelog-github` instalados
- Config: `access: public`, changelog GitHub, base `main`
- Scripts: `changeset`, `version-packages`, `publish-packages`
- Release workflow: `.github/workflows/release.yml`
- **Cada alteração bumps versão** via `pnpm changeset` + `pnpm changeset version`
- Versão atual: `@hercules/cli` 0.2.2, demais pacotes 0.2.1

### Tools + autoConfigure + MCP
- `exec.ts` e `shell.ts`: usam `bootstrap.ts` com tools reais (exec, file, browser, **mcp_call** = 9 tools)
- `ModelRouter.autoConfigure()` chamado na inicialização
- **MCP**: `createMcpTool()` registrado no bootstrap, permite chamar servidores MCP dinamicamente

### Logger estruturado
- `logger.ts`: info/warn/error/debug/stdout
- Controlado por `HERCULES_LOG_LEVEL`
- Meta em key=value ou JSON via `HERCULES_LOG_JSON`
- Adotado em exec.ts, status.ts, update.ts, shell.ts

### Streaming SSE real
- `ModelRequest.onDelta` callback adicionado
- `AgentLoop` emite eventos `text_delta` via `onDelta`
- **OpenAI-compatible** (OpenAI, Groq, DeepSeek, etc): SSE parsing com `getReader()`
- **Ollama**: SSE streaming com parsing linha a linha
- `handleOpenAIStream()` e `handleOllamaStream()` implementados
- `hercules exec --stream` e `hercules shell --stream` com output em tempo real

### CI
- `.github/workflows/ci.yml`: build + lint + test em PR/push
- `hercules --version` lê version real do `package.json`
- `hercules status -v` mostra tools, updates, streaming

### Testes
- `cli.test.ts`: 14 testes (logger 6, bootstrap 3, exec/shell/status/index/update 5)
- Build: zero erros em todos os 11 pacotes

## Pendências
- `@hercules/core` 0.2.1 — streaming provider test coverage
- `@hercules/tools` 0.2.1 — MCP client test coverage
- Gateway WebSocket stub (`send()` vazio) — não funcional
