/**
 * Claude Code model aliases supported by the CLI (`--model`).
 * @module constants/claudeModels
 */

export interface ClaudeModelOption {
  value: string | null
  label: string
  description?: string
}

/** Selectable models for NightForge runs and compose. */
export const CLAUDE_MODEL_OPTIONS: ClaudeModelOption[] = [
  {
    value: null,
    label: 'Défaut (session / CLI)',
    description: 'Conserve le modèle de la session ou le défaut Claude Code',
  },
  { value: 'fable', label: 'Fable 5', description: 'Alias CLI : fable' },
  { value: 'opus', label: 'Opus 4.8', description: 'Alias CLI : opus' },
  { value: 'sonnet', label: 'Sonnet', description: 'Alias CLI : sonnet' },
  { value: 'haiku', label: 'Haiku', description: 'Alias CLI : haiku' },
]

/**
 * Human label for a stored model alias.
 * @param model - Model alias or null.
 * @returns Display label.
 */
export function claudeModelLabel(model?: string | null): string | null {
  if (!model) {
    return null
  }
  return CLAUDE_MODEL_OPTIONS.find((option) => option.value === model)?.label ?? model
}
