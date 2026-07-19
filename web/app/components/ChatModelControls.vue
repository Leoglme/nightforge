<template>
  <div class="flex flex-wrap items-center justify-end gap-1 px-0.5 sm:gap-1.5">
    <span
      v-if="fastMode && showFast"
      class="mr-auto rounded-md bg-[var(--app-accent-soft)] px-2 py-1 text-[0.65rem] font-medium text-[var(--app-accent-ink)]"
    >
      Fast
    </span>

    <slot name="start" />

    <UPopover v-model:open="modelOpen" :ui="{ content: 'p-0 w-[min(18rem,calc(100vw-1.5rem))]' }">
      <button
        type="button"
        class="inline-flex min-h-9 cursor-pointer items-center gap-1.5 rounded-lg px-2 text-xs font-medium text-[var(--app-ink)] transition-colors hover:bg-[var(--app-surface-2)] sm:min-h-8"
      >
        <CursorLogo v-if="provider === 'cursor'" class="!h-3.5 !w-3.5" />
        <ClaudeLogo v-else class="!h-3.5 !w-3.5" />
        <span class="max-w-[10rem] truncate">{{ modelPillLabel }}</span>
      </button>

      <template #content>
        <div class="flex flex-col py-1.5">
          <div v-for="group in modelGroups" :key="group.provider" class="py-1">
            <p class="app-label flex items-center gap-1.5 px-3 py-1.5">
              <CursorLogo v-if="group.provider === 'cursor'" class="!h-3 !w-3" />
              <ClaudeLogo v-else class="!h-3 !w-3" />
              {{ group.label }}
            </p>
            <button
              v-for="(item, index) in group.models"
              :key="`${group.provider}-${item.id}`"
              type="button"
              class="flex w-full cursor-pointer items-center gap-2 px-3 py-2 text-left text-sm transition-colors hover:bg-[var(--app-surface-2)]"
              @click="selectModel(group.provider, item.id)"
            >
              <UIcon
                name="i-lucide-check"
                class="h-3.5 w-3.5 shrink-0"
                :class="provider === group.provider && model === item.id ? 'text-[var(--app-ink)]' : 'opacity-0'"
              />
              <span class="min-w-0 flex-1 truncate text-[var(--app-ink)]">{{ item.label }}</span>
              <span class="font-mono text-[0.65rem] text-[var(--app-ink-soft)]">{{ index + 1 }}</span>
            </button>
          </div>

          <div v-if="showFast" class="border-t border-[var(--app-line)] px-3 py-2.5">
            <p class="app-label mb-2">{{ t('runs.chat.fastMode') }}</p>
            <label class="flex cursor-pointer items-center justify-between gap-3 text-sm text-[var(--app-ink)]">
              <span>{{ t('runs.chat.enableFast') }}</span>
              <USwitch
                :model-value="fastMode"
                size="sm"
                @update:model-value="emit('update:fastMode', Boolean($event))"
              />
            </label>
          </div>
        </div>
      </template>
    </UPopover>

    <UPopover
      v-if="effortOptions.length"
      v-model:open="effortOpen"
      :ui="{ content: 'p-3 w-[min(18rem,calc(100vw-1.5rem))]' }"
    >
      <button
        type="button"
        class="inline-flex min-h-9 cursor-pointer items-center gap-1 rounded-lg bg-[var(--app-surface-2)] px-2.5 text-xs font-medium text-[var(--app-ink)] transition-colors hover:bg-[var(--app-line)] sm:min-h-8"
      >
        {{ effortPillLabel }}
      </button>

      <template #content>
        <div class="flex flex-col gap-3">
          <p class="text-sm font-medium text-[var(--app-ink)]">
            {{ t('runs.chat.effortTitle', { level: effortPillLabel }) }}
          </p>
          <div class="flex items-center justify-between text-[0.65rem] text-[var(--app-ink-soft)]">
            <span>{{ t('runs.chat.faster') }}</span>
            <span>{{ t('runs.chat.smarter') }}</span>
          </div>
          <USlider
            :model-value="effortIndex"
            :min="0"
            :max="Math.max(effortOptions.length - 1, 0)"
            :step="1"
            color="neutral"
            size="md"
            class="px-1"
            :aria-label="t('runs.chat.effort')"
            @update:model-value="onEffortSlide"
          />
          <div class="flex justify-between px-0.5 font-mono text-[0.6rem] text-[var(--app-ink-soft)]">
            <span v-for="opt in effortOptions" :key="`lbl-${opt.value}`" class="min-w-0 flex-1 text-center">
              {{ opt.short }}
            </span>
          </div>
        </div>
      </template>
    </UPopover>
  </div>
</template>

<script lang="ts" setup>
import { computed, ref } from 'vue'
import type { AiProvider, EffortLevel } from '~/constants/modelPresets'
import {
  CLAUDE_MODELS,
  CURSOR_MODELS,
  EFFORT_LABELS,
  defaultEffortFor,
  findModelPreset,
  modelLabel,
  supportsFast,
} from '~/constants/modelPresets'

/**
 * Shared Claude Code–style model + effort pills (Compose + run chat).
 */
const props = defineProps<{
  provider: AiProvider | null
  model: string | null
  effort: string | null
  fastMode: boolean
}>()

const emit = defineEmits<{
  'update:provider': [value: AiProvider | null]
  'update:model': [value: string | null]
  'update:effort': [value: string | null]
  'update:fastMode': [value: boolean]
}>()

const { t } = useI18n()
const modelOpen = ref(false)
const effortOpen = ref(false)

const modelGroups = computed(() => [
  { provider: 'claude' as const, label: t('runs.chat.claude'), models: CLAUDE_MODELS },
  { provider: 'cursor' as const, label: t('runs.chat.cursor'), models: CURSOR_MODELS },
])

const modelPillLabel = computed(() => {
  const label = modelLabel(props.provider, props.model)
  if (label) {
    return label
  }
  return props.provider === 'cursor' ? t('runs.chat.cursor') : t('runs.chat.claude')
})

const effortOptions = computed(() => {
  const preset = findModelPreset(props.provider, props.model)
  if (!preset?.efforts.length) {
    return []
  }
  return preset.efforts.map((value) => {
    const key = `runs.chat.effortLevels.${value}`
    const translated = t(key)
    const label = translated !== key ? translated : (EFFORT_LABELS[value] ?? value)
    return {
      value,
      label,
      short: label.length > 5 ? label.slice(0, 3) : label,
    }
  })
})

const effortIndex = computed(() => {
  const idx = effortOptions.value.findIndex((opt) => opt.value === props.effort)
  return idx >= 0 ? idx : Math.max(effortOptions.value.length - 1, 0)
})

const effortPillLabel = computed(() => {
  if (!props.effort) {
    return t('runs.chat.effort')
  }
  const key = `runs.chat.effortLevels.${props.effort}`
  const translated = t(key)
  return translated !== key ? translated : (EFFORT_LABELS[props.effort as EffortLevel] ?? props.effort)
})

const showFast = computed(() => supportsFast(props.provider, props.model))

/**
 * Pick a model and reset effort / fast defaults.
 */
function selectModel(nextProvider: AiProvider, modelId: string): void {
  emit('update:provider', nextProvider)
  emit('update:model', modelId)
  emit('update:effort', defaultEffortFor(nextProvider, modelId))
  const preset = findModelPreset(nextProvider, modelId)
  emit('update:fastMode', Boolean(preset?.defaultFast))
  modelOpen.value = false
}

/**
 * Drag/slide effort — keep the popover open (desktop + mobile).
 */
function onEffortSlide(value: number | number[]): void {
  const raw = Array.isArray(value) ? value[0] : value
  const index = Math.round(Number(raw))
  const opt = effortOptions.value[index]
  if (opt) {
    emit('update:effort', opt.value)
  }
}
</script>
