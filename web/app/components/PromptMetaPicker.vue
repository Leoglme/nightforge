<template>
  <div :class="['flex flex-col gap-2', compact ? '' : '']">
    <div class="grid grid-cols-1 gap-2 sm:grid-cols-2">
      <USelectMenu
        :model-value="provider"
        :items="providerItems"
        value-key="value"
        label-key="label"
        placeholder="Provider"
        icon="i-lucide-bot"
        class="w-full"
        :ui="{ content: 'z-[60]' }"
        @update:model-value="onProvider"
      />
      <USelectMenu
        :model-value="model"
        :items="modelItems"
        value-key="value"
        label-key="label"
        placeholder="Modèle"
        icon="i-lucide-cpu"
        class="w-full"
        :ui="{ content: 'z-[60]' }"
        :disabled="!provider"
        @update:model-value="onModel"
      />
    </div>
    <div class="flex flex-wrap items-center gap-3">
      <USelectMenu
        v-if="effortOptions.length"
        :model-value="effort"
        :items="effortOptions"
        value-key="value"
        label-key="label"
        placeholder="Effort"
        icon="i-lucide-gauge"
        class="w-full min-w-[8rem] sm:w-40"
        :ui="{ content: 'z-[60]' }"
        @update:model-value="emit('update:effort', $event)"
      />
      <label v-if="showFast" class="flex items-center gap-2 text-xs text-[var(--app-ink-soft)]">
        <USwitch :model-value="fastMode" size="sm" @update:model-value="emit('update:fastMode', Boolean($event))" />
        Fast
      </label>
    </div>
  </div>
</template>

<script lang="ts" setup>
import { computed } from 'vue'
import type { AiProvider, EffortLevel } from '~/constants/modelPresets'
import {
  EFFORT_LABELS,
  PROVIDER_OPTIONS,
  defaultEffortFor,
  modelsForProvider,
  supportsFast,
} from '~/constants/modelPresets'

/**
 * Provider / model / effort / fast picker shared by Queue and Composer.
 */
const props = defineProps<{
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

const providerItems = PROVIDER_OPTIONS.map((p) => ({
  value: p.value,
  label: p.label,
}))

const modelItems = computed(() =>
  modelsForProvider(props.provider).map((m) => ({
    value: m.id,
    label: m.label,
  })),
)

const effortOptions = computed(() => {
  const preset = modelsForProvider(props.provider).find((m) => m.id === props.model)
  if (!preset?.efforts.length) {
    return []
  }
  return preset.efforts.map((level) => ({
    value: level,
    label: EFFORT_LABELS[level as EffortLevel] ?? level,
  }))
})

const showFast = computed(() => supportsFast(props.provider, props.model))

/**
 * When provider changes, reset model to first preset with its defaults.
 */
function onProvider(value: AiProvider | null): void {
  emit('update:provider', value)
  const models = modelsForProvider(value)
  const next = models[0] ?? null
  emit('update:model', next?.id ?? null)
  emit('update:effort', next?.defaultEffort ?? null)
  emit('update:fastMode', next?.defaultFast ?? false)
}

/**
 * When model changes, apply daily defaults for effort / fast.
 */
function onModel(value: string | null): void {
  emit('update:model', value)
  emit('update:effort', defaultEffortFor(props.provider, value))
  emit('update:fastMode', false)
}
</script>
