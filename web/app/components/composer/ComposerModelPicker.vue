<template>
  <div :class="compact ? '' : 'rounded-lg border border-[var(--app-line)] bg-[var(--app-surface-2)] p-3'">
    <div :class="['flex items-center gap-1.5', compact ? 'mb-1.5' : 'mb-2']">
      <UIcon name="i-lucide-cpu" class="text-[var(--app-accent)]" />
      <span class="app-label">Provider & modèle</span>
    </div>

    <PromptMetaPicker
      :provider="provider"
      :model="model"
      :effort="effort"
      :fast-mode="fastMode"
      :compact="compact"
      @update:provider="emit('update:provider', $event)"
      @update:model="emit('update:model', $event)"
      @update:effort="emit('update:effort', $event)"
      @update:fast-mode="emit('update:fastMode', $event)"
    />
  </div>
</template>

<script lang="ts" setup>
import type { AiProvider } from '~/constants/modelPresets'

/**
 * Provider / model / effort / fast picker for the Composer.
 */
defineProps<{
  provider: AiProvider | null
  model: string | null
  effort: string | null
  fastMode: boolean
  compact?: boolean
}>()

const emit = defineEmits<{
  'update:provider': [value: AiProvider | null]
  'update:model': [value: string | null]
  'update:effort': [value: string | null]
  'update:fastMode': [value: boolean]
}>()
</script>
