<template>
  <div :class="compact ? '' : 'rounded-lg border border-[var(--app-line)] bg-[var(--app-surface-2)] p-3'">
    <div :class="['flex items-center gap-1.5', compact ? 'mb-1.5' : 'mb-2']">
      <UIcon name="i-lucide-cpu" class="text-[var(--app-accent)]" />
      <span class="app-label">Modèle Claude</span>
    </div>

    <USelectMenu
      :model-value="modelValue"
      :items="options"
      value-key="value"
      label-key="label"
      class="w-full"
      :ui="{ content: 'z-[60]' }"
      @update:model-value="emit('update:modelValue', $event)"
    />

    <p v-if="selectedDescription && !compact" class="mt-2 text-xs text-[var(--app-ink-soft)]">
      {{ selectedDescription }}
    </p>
  </div>
</template>

<script lang="ts" setup>
import { computed } from 'vue'
import { CLAUDE_MODEL_OPTIONS } from '~/constants/claudeModels'

/**
 * Picker for the Claude Code model alias passed to `--model`.
 */
const props = defineProps<{
  modelValue: string | null
  compact?: boolean
}>()

const emit = defineEmits<{
  'update:modelValue': [value: string | null]
}>()

const options = CLAUDE_MODEL_OPTIONS

const selectedDescription = computed(() => options.find((option) => option.value === props.modelValue)?.description)
</script>
