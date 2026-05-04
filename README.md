# Hercules Agent

Modular AI Agent Framework com 10 módulos principais:

- **Voice** - TTS/STT (Edge, ElevenLabs, OpenAI, Whisper)
- **Webhooks** - Triggers externos para o agente
- **Cron Jobs** - Tarefas agendadas
- **Profiles** - Múltiplos perfiles isolados
- **Plugins** - Sistema de extensões
- **Context Compression** - Auto-compressão de conversas longas
- **Browser** - Automação via CDP (Playwright)
- **Vision** - Análise de imagens (GPT-4V, Claude, Groq)
- **Multi-Agent** - Execução de sub-agentes
- **Approval Manager** - Aprovar/denegar comandos perigosos

## Instalação

```bash
pip install hercules-agent
```

## Uso

```python
from hercules_agent import VoiceManager, VisionManager, MultiAgentManager

# Voice
voice = VoiceManager()
await voice.speak("Hello!")

# Vision
vision = VisionManager()
result = await vision.analyze("image.jpg", "Describe this image")

# Multi-Agent
manager = MultiAgentManager(executor_fn=my_executor)
agent = await manager.spawn(goal="Research topic", name="researcher")
result = await manager.execute(agent.id)
```

## CLI

```bash
hercules --help
```