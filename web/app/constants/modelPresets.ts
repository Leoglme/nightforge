/**
 * Multi-provider model presets for NightForge (Claude Code + Cursor Agent).
 * Defaults match Léo's daily usage for quick capture.
 * @module constants/modelPresets
 */

export type AiProvider = 'claude' | 'cursor'

export type EffortLevel = 'low' | 'medium' | 'high' | 'xhigh' | 'max'

export interface ModelPreset {
  /** Stable id stored in DB / sent to CLI */
  id: string
  label: string
  description?: string
  /** Effort levels this model supports (empty = no effort UI) */
  efforts: EffortLevel[]
  /** Default effort when selecting this model */
  defaultEffort: EffortLevel | null
  /** Whether a fast toggle is available */
  supportsFast: boolean
  /** Default for fast (always false for Léo's prefs) */
  defaultFast: boolean
}

export interface ProviderOption {
  value: AiProvider
  label: string
  description: string
}

export const PROVIDER_OPTIONS: ProviderOption[] = [
  {
    value: 'claude',
    label: 'Claude Code',
    description: 'CLI Claude Max (`claude -p`)',
  },
  {
    value: 'cursor',
    label: 'Cursor',
    description: 'Cursor Agent CLI (`agent -p`)',
  },
]

export const EFFORT_LABELS: Record<EffortLevel, string> = {
  low: 'Low',
  medium: 'Medium',
  high: 'High',
  xhigh: 'Extra',
  max: 'Max',
}

/** Claude Code models */
export const CLAUDE_MODELS: ModelPreset[] = [
  {
    id: 'sonnet',
    label: 'Sonnet 5',
    description: 'Alias CLI : sonnet — effort max',
    efforts: ['low', 'medium', 'high', 'xhigh', 'max'],
    defaultEffort: 'max',
    supportsFast: false,
    defaultFast: false,
  },
  {
    id: 'opus',
    label: 'Opus 4.8',
    description: 'Alias CLI : opus — effort high',
    efforts: ['low', 'medium', 'high', 'xhigh', 'max'],
    defaultEffort: 'high',
    supportsFast: false,
    defaultFast: false,
  },
  {
    id: 'fable',
    label: 'Fable 5',
    description: 'Alias CLI : fable — effort extra (xhigh)',
    efforts: ['low', 'medium', 'high', 'xhigh', 'max'],
    defaultEffort: 'xhigh',
    supportsFast: false,
    defaultFast: false,
  },
  {
    id: 'haiku',
    label: 'Haiku',
    description: 'Alias CLI : haiku',
    efforts: ['low', 'medium', 'high'],
    defaultEffort: 'high',
    supportsFast: false,
    defaultFast: false,
  },
]

/** Cursor Agent models */
export const CURSOR_MODELS: ModelPreset[] = [
  {
    id: 'grok-4.5',
    label: 'Grok 4.5',
    description: 'Effort high (max disponible)',
    efforts: ['low', 'medium', 'high'],
    defaultEffort: 'high',
    supportsFast: true,
    defaultFast: false,
  },
  {
    id: 'composer-2.5',
    label: 'Composer 2.5',
    description: 'Pas d’effort — toggle fast uniquement',
    efforts: [],
    defaultEffort: null,
    supportsFast: true,
    defaultFast: false,
  },
  {
    id: 'opus',
    label: 'Opus 4.8',
    description: 'Même config que Claude Code',
    efforts: ['low', 'medium', 'high', 'xhigh', 'max'],
    defaultEffort: 'high',
    supportsFast: true,
    defaultFast: false,
  },
  {
    id: 'fable',
    label: 'Fable 5',
    description: 'Même config que Claude Code',
    efforts: ['low', 'medium', 'high', 'xhigh', 'max'],
    defaultEffort: 'xhigh',
    supportsFast: true,
    defaultFast: false,
  },
  {
    id: 'sonnet',
    label: 'Sonnet 5',
    description: 'Même config que Claude Code',
    efforts: ['low', 'medium', 'high', 'xhigh', 'max'],
    defaultEffort: 'max',
    supportsFast: true,
    defaultFast: false,
  },
]

/**
 * Models available for a provider.
 */
export function modelsForProvider(provider: AiProvider | null | undefined): ModelPreset[] {
  if (provider === 'cursor') {
    return CURSOR_MODELS
  }
  return CLAUDE_MODELS
}

/**
 * Find a model preset.
 */
export function findModelPreset(
  provider: AiProvider | null | undefined,
  modelId: string | null | undefined,
): ModelPreset | null {
  if (!modelId) {
    return null
  }
  return modelsForProvider(provider).find((m) => m.id === modelId) ?? null
}

/**
 * Default effort for a provider/model pair.
 */
export function defaultEffortFor(
  provider: AiProvider | null | undefined,
  modelId: string | null | undefined,
): EffortLevel | null {
  return findModelPreset(provider, modelId)?.defaultEffort ?? null
}

/**
 * Whether fast mode is supported.
 */
export function supportsFast(provider: AiProvider | null | undefined, modelId: string | null | undefined): boolean {
  return findModelPreset(provider, modelId)?.supportsFast ?? false
}

/**
 * Human label for a stored model id.
 */
export function modelLabel(provider: AiProvider | null | undefined, modelId: string | null | undefined): string | null {
  if (!modelId) {
    return null
  }
  return findModelPreset(provider, modelId)?.label ?? modelId
}

/**
 * Human label for a provider.
 */
export function providerLabel(provider: AiProvider | null | undefined): string | null {
  if (!provider) {
    return null
  }
  return PROVIDER_OPTIONS.find((p) => p.value === provider)?.label ?? provider
}

/**
 * Build a short meta badge string for copy / list UI.
 */
export function formatPromptMeta(opts: {
  provider?: AiProvider | null
  model?: string | null
  effort?: string | null
  fastMode?: boolean
}): string {
  const parts: string[] = []
  const pLabel = providerLabel(opts.provider)
  if (pLabel) {
    parts.push(pLabel)
  }
  const mLabel = modelLabel(opts.provider, opts.model)
  if (mLabel) {
    parts.push(mLabel)
  }
  if (opts.effort) {
    parts.push(EFFORT_LABELS[opts.effort as EffortLevel] ?? opts.effort)
  }
  if (opts.fastMode) {
    parts.push('fast')
  }
  return parts.length ? `[${parts.join(' · ')}]` : ''
}

/** @deprecated Use CLAUDE_MODELS / modelPresets — kept for older imports */
export interface ClaudeModelOption {
  value: string | null
  label: string
  description?: string
}

/** @deprecated Prefer modelsForProvider('claude') */
export const CLAUDE_MODEL_OPTIONS: ClaudeModelOption[] = [
  {
    value: null,
    label: 'Défaut (session / CLI)',
    description: 'Conserve le modèle de la session ou le défaut Claude Code',
  },
  ...CLAUDE_MODELS.map((m) => ({
    value: m.id,
    label: m.label,
    description: m.description,
  })),
]

/**
 * @deprecated Prefer modelLabel
 */
export function claudeModelLabel(model?: string | null): string | null {
  return modelLabel('claude', model)
}
