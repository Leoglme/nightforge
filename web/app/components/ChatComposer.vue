<template>
  <div :class="fullWidth ? 'w-full' : 'mx-auto w-full max-w-4xl xl:max-w-5xl'">
    <UFormField v-if="projectOptions.length > 1" :label="t('runs.chat.project')" class="mb-2.5">
      <USelectMenu
        :model-value="projectId"
        :items="projectOptions"
        value-key="value"
        label-key="label"
        class="w-full"
        @update:model-value="emit('update:projectId', $event)"
      />
    </UFormField>

    <div
      class="relative rounded-2xl border border-[var(--app-line)] bg-[var(--app-surface-2)] transition-[border-color] duration-200 focus-within:border-[var(--app-ink-soft)]"
    >
      <textarea
        ref="inputEl"
        :value="text"
        rows="1"
        :placeholder="placeholder || t('runs.chat.placeholder')"
        class="max-h-48 min-h-[2.5rem] w-full resize-none overflow-y-auto bg-transparent py-2.5 pr-12 pl-3.5 text-sm leading-normal text-[var(--app-ink)] outline-none placeholder:text-[var(--app-ink-soft)] sm:min-h-[2.625rem] sm:py-2.5 sm:pr-12 sm:pl-4 sm:text-[0.9375rem]"
        @input="onInput"
        @keydown.enter.exact.prevent="trySend"
      />
      <button
        type="button"
        class="absolute right-2 bottom-1.5 flex h-8 w-8 cursor-pointer items-center justify-center rounded-lg transition-all duration-200 disabled:cursor-not-allowed sm:right-2.5 sm:bottom-2"
        :class="
          canSend
            ? 'bg-[var(--app-ink)] text-[var(--app-surface)] hover:opacity-90'
            : 'bg-transparent text-[var(--app-ink-soft)] opacity-35'
        "
        :disabled="!canSend || loading"
        :aria-label="t('runs.chat.send')"
        @click="trySend"
      >
        <UIcon
          :name="loading ? 'i-lucide-loader-circle' : 'i-lucide-corner-down-left'"
          :class="['h-3.5 w-3.5', loading ? 'animate-spin' : '']"
        />
      </button>
    </div>

    <div class="mt-2 flex flex-wrap items-center gap-2">
      <div v-if="hint || showContinue" class="flex min-w-0 flex-1 flex-wrap items-center gap-1">
        <p v-if="hint" class="text-xs text-[var(--app-ink-soft)]">{{ hint }}</p>
        <UButton
          v-if="showContinue"
          size="xs"
          color="neutral"
          variant="ghost"
          icon="i-lucide-play"
          @click="emit('continue')"
        >
          {{ continueLabel || t('compose.continue') }}
        </UButton>
      </div>
      <ChatModelControls
        class="ml-auto"
        :provider="provider"
        :model="model"
        :effort="effort"
        :fast-mode="fastMode"
        @update:provider="emit('update:provider', $event)"
        @update:model="emit('update:model', $event)"
        @update:effort="emit('update:effort', $event)"
        @update:fast-mode="emit('update:fastMode', $event)"
      >
        <template v-if="$slots.controlsStart" #start>
          <slot name="controlsStart" />
        </template>
      </ChatModelControls>
    </div>
  </div>
</template>

<script lang="ts" setup>
import { nextTick, ref } from 'vue'
import type { AiProvider } from '~/constants/modelPresets'

/**
 * Shared Claude Code–style chat composer (run page + Compose).
 */
const props = withDefaults(
  defineProps<{
    text: string
    provider: AiProvider | null
    model: string | null
    effort: string | null
    fastMode: boolean
    projectId?: number
    projectOptions?: { label: string; value: number }[]
    canSend: boolean
    loading?: boolean
    placeholder?: string
    hint?: string
    showContinue?: boolean
    continueLabel?: string
    /** Skip max-width centering (Compose column already constrains width). */
    fullWidth?: boolean
  }>(),
  {
    projectOptions: () => [],
    loading: false,
    showContinue: false,
    fullWidth: false,
  },
)

const emit = defineEmits<{
  'update:text': [value: string]
  'update:provider': [value: AiProvider | null]
  'update:model': [value: string | null]
  'update:effort': [value: string | null]
  'update:fastMode': [value: boolean]
  'update:projectId': [value: number | undefined]
  send: []
  continue: []
}>()

const { t } = useI18n()
const inputEl = ref<HTMLTextAreaElement | null>(null)

/**
 * Grow the textarea with content (capped via CSS max-height).
 */
function onInput(event: Event): void {
  const el = event.target as HTMLTextAreaElement
  emit('update:text', el.value)
  el.style.height = '0px'
  el.style.height = `${Math.min(Math.max(el.scrollHeight, 40), 192)}px`
}

/**
 * Send when the composer is ready.
 */
function trySend(): void {
  if (!props.canSend || props.loading) {
    return
  }
  emit('send')
  nextTick(() => {
    if (inputEl.value) {
      inputEl.value.style.height = ''
    }
  })
}
</script>
