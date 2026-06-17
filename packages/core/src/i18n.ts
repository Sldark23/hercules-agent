export interface I18nConfig {
  locale: string
  fallbackLocale: string
  messages: Record<string, Record<string, string>>
}

const DEFAULT_MESSAGES: Record<string, Record<string, string>> = {
  'en': {
    'agent.thinking': 'Thinking...',
    'agent.error': 'An error occurred: {error}',
    'agent.max_turns': 'Reached maximum turns ({max}).',
    'agent.tool_call': 'Calling tool: {tool}',
    'agent.tool_result': 'Tool result received.',
    'session.created': 'Session created.',
    'session.ended': 'Session ended.',
    'memory.saved': 'Memory saved.',
    'memory.recalled': 'Recalled {count} memories.',
    'job.scheduled': 'Job "{name}" scheduled ({id}).',
    'job.executed': 'Job "{name}" executed.',
    'job.failed': 'Job "{name}" failed: {error}',
    'run.started': 'Run "{name}" started.',
    'run.completed': 'Run "{name}" completed.',
    'run.failed': 'Run "{name}" failed: {error}',
    'skill.activated': 'Skill "{name}" activated.',
    'skill.deactivated': 'Skill "{name}" deactivated.',
    'plugin.loaded': 'Plugin "{name}" loaded.',
    'gateway.started': 'Gateway listening on {url}.',
    'channel.connected': 'Channel "{name}" connected.',
    'channel.disconnected': 'Channel "{name}" disconnected.',
  },
  'pt-BR': {
    'agent.thinking': 'Pensando...',
    'agent.error': 'Ocorreu um erro: {error}',
    'agent.max_turns': 'Atingiu o máximo de turnos ({max}).',
    'agent.tool_call': 'Chamando ferramenta: {tool}',
    'agent.tool_result': 'Resultado da ferramenta recebido.',
    'session.created': 'Sessão criada.',
    'session.ended': 'Sessão encerrada.',
    'memory.saved': 'Memória salva.',
    'memory.recalled': 'Recuperadas {count} memórias.',
    'job.scheduled': 'Tarefa "{name}" agendada ({id}).',
    'job.executed': 'Tarefa "{name}" executada.',
    'job.failed': 'Tarefa "{name}" falhou: {error}',
    'run.started': 'Execução "{name}" iniciada.',
    'run.completed': 'Execução "{name}" concluída.',
    'run.failed': 'Execução "{name}" falhou: {error}',
    'skill.activated': 'Habilidade "{name}" ativada.',
    'skill.deactivated': 'Habilidade "{name}" desativada.',
    'plugin.loaded': 'Plugin "{name}" carregado.',
    'gateway.started': 'Gateway ouvindo em {url}.',
    'channel.connected': 'Canal "{name}" conectado.',
    'channel.disconnected': 'Canal "{name}" desconectado.',
  },
  'es': {
    'agent.thinking': 'Pensando...',
    'agent.error': 'Ocurrió un error: {error}',
    'agent.max_turns': 'Alcanzó el máximo de turnos ({max}).',
    'agent.tool_call': 'Llamando herramienta: {tool}',
    'agent.tool_result': 'Resultado de herramienta recibido.',
    'session.created': 'Sesión creada.',
    'session.ended': 'Sesión finalizada.',
    'memory.saved': 'Memoria guardada.',
    'memory.recalled': 'Recuperadas {count} memorias.',
    'job.scheduled': 'Tarea "{name}" programada ({id}).',
    'job.executed': 'Tarea "{name}" ejecutada.',
    'job.failed': 'Tarea "{name}" falló: {error}',
    'run.started': 'Ejecución "{name}" iniciada.',
    'run.completed': 'Ejecución "{name}" completada.',
    'run.failed': 'Ejecución "{name}" falló: {error}',
    'skill.activated': 'Habilidad "{name}" activada.',
    'skill.deactivated': 'Habilidad "{name}" desactivada.',
    'plugin.loaded': 'Plugin "{name}" cargado.',
    'gateway.started': 'Gateway escuchando en {url}.',
    'channel.connected': 'Canal "{name}" conectado.',
    'channel.disconnected': 'Canal "{name}" desconectado.',
  },
}

export class I18n {
  private config: I18nConfig

  constructor(config?: Partial<I18nConfig>) {
    this.config = {
      locale: config?.locale ?? 'en',
      fallbackLocale: config?.fallbackLocale ?? 'en',
      messages: { ...DEFAULT_MESSAGES, ...config?.messages },
    }
  }

  t(key: string, params?: Record<string, string | number>): string {
    const localeMessages = this.config.messages[this.config.locale]
    const fallbackMessages = this.config.messages[this.config.fallbackLocale]

    let template = localeMessages?.[key] ?? fallbackMessages?.[key] ?? key
    if (params) {
      for (const [k, v] of Object.entries(params)) {
        template = template.replace(`{${k}}`, String(v))
      }
    }
    return template
  }

  setLocale(locale: string): void {
    this.config.locale = locale
  }

  getLocale(): string {
    return this.config.locale
  }

  addMessages(locale: string, messages: Record<string, string>): void {
    this.config.messages[locale] = { ...this.config.messages[locale], ...messages }
  }

  hasLocale(locale: string): boolean {
    return !!this.config.messages[locale]
  }

  availableLocales(): string[] {
    return Object.keys(this.config.messages)
  }
}

let globalI18n: I18n | null = null

export function getI18n(): I18n {
  if (!globalI18n) {
    globalI18n = new I18n()
  }
  return globalI18n
}

export function setI18n(i18n: I18n): void {
  globalI18n = i18n
}
