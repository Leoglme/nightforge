<template>
  <article class="flex flex-col gap-6 sm:gap-7">
    <!-- User: gray card (Cursor / Claude pattern) -->
    <div class="flex justify-end">
      <div
        class="w-full max-w-[min(42rem,100%)] rounded-2xl rounded-br-md border border-[var(--app-line)] bg-[var(--app-surface-2)] px-3 py-2.5 sm:max-w-[min(42rem,94%)] sm:px-3.5"
      >
        <div class="mb-1.5 flex items-start justify-between gap-2 sm:items-center sm:gap-3">
          <span class="shrink-0 text-xs font-medium text-[var(--app-ink-soft)]">{{ t('runs.chat.you') }}</span>
          <span
            v-if="modelOnlyLabel || projectName"
            class="inline-flex max-w-[75%] min-w-0 flex-wrap items-center justify-end gap-x-1.5 gap-y-0.5 text-right text-xs text-[var(--app-ink-soft)] sm:max-w-none"
          >
            <template v-if="modelOnlyLabel">
              <CursorLogo v-if="provider === 'cursor'" class="!h-3.5 !w-3.5" />
              <ClaudeLogo v-else class="!h-3.5 !w-3.5" />
              <span class="truncate">{{ modelOnlyLabel }}</span>
              <span v-if="effortLabel" class="shrink-0 opacity-70">· {{ effortLabel }}</span>
              <span v-if="message.fast_mode" class="shrink-0 text-[var(--app-accent-ink)]">· Fast</span>
            </template>
            <span v-if="projectName" class="min-w-0 truncate opacity-70">· {{ projectName }}</span>
          </span>
        </div>
        <p class="text-sm leading-relaxed break-words whitespace-pre-wrap text-[var(--app-ink)]">
          {{ message.content }}
        </p>
      </div>
    </div>

    <!-- Assistant: plain text, no card -->
    <div class="w-full max-w-[min(46rem,100%)]">
      <div class="mb-2 flex flex-wrap items-center gap-2">
        <span class="inline-flex min-w-0 items-center gap-1.5 text-xs font-medium text-[var(--app-ink-soft)]">
          <CursorLogo v-if="provider === 'cursor'" class="!h-3.5 !w-3.5 shrink-0" />
          <ClaudeLogo v-else class="!h-3.5 !w-3.5 shrink-0" />
          <span class="truncate">{{ modelOnlyLabel || assistantFallback }}</span>
        </span>
        <StatusBadge :status="message.status" dot />
      </div>

      <div v-if="message.status === 'PENDING'" class="text-sm text-[var(--app-ink-soft)]">
        {{ t('runs.chat.waiting') }}
      </div>

      <div
        v-else-if="message.status === 'RUNNING' && events.length === 0"
        class="flex items-center gap-2 text-sm text-[var(--app-ink-soft)]"
      >
        <span class="inline-flex gap-1" aria-hidden="true">
          <span class="size-1.5 animate-pulse rounded-full bg-[var(--app-accent-ink)]" />
          <span class="size-1.5 animate-pulse rounded-full bg-[var(--app-accent-ink)] [animation-delay:120ms]" />
          <span class="size-1.5 animate-pulse rounded-full bg-[var(--app-accent-ink)] [animation-delay:240ms]" />
        </span>
        {{ t('runs.chat.thinking') }}
      </div>

      <div
        v-else-if="events.length"
        class="max-h-[36vh] space-y-1 overflow-y-auto text-sm leading-relaxed sm:max-h-[40vh]"
      >
        <p v-for="ev in events" :key="ev.id" :class="['break-words whitespace-pre-wrap', eventClass(ev.level)]">
          {{ ev.message }}
        </p>
      </div>

      <p v-else-if="message.status === 'DONE'" class="text-sm text-[var(--app-ink-soft)]">
        {{ t('runs.chat.done') }}
      </p>

      <p
        v-else-if="message.status === 'FAILED' || message.status === 'SKIPPED'"
        class="text-sm break-words text-[var(--app-red)]"
      >
        {{ message.error || t('runs.chat.failed') }}
      </p>

      <p
        v-if="message.error && message.status === 'FAILED' && events.length"
        class="mt-2 text-sm break-words text-[var(--app-red)]"
      >
        {{ message.error }}
      </p>

      <div v-if="canRetry" class="mt-3 flex justify-end">
        <UButton
          size="xs"
          color="neutral"
          variant="outline"
          icon="i-lucide-rotate-ccw"
          :loading="retrying"
          class="min-h-9 min-w-9 sm:min-h-0"
          @click="emit('retry')"
        >
          {{ t('runs.chat.retry') }}
        </UButton>
      </div>
    </div>
  </article>
</template>

<script lang="ts" setup>
import { computed } from 'vue'
import type { AiProvider, EffortLevel } from '~/constants/modelPresets'
import { EFFORT_LABELS, modelLabel } from '~/constants/modelPresets'
import type { RunEvent, RunMessage } from '~/types'

/**
 * One chat turn: user gray card + AI plain text (Cursor / Claude layout).
 */
const props = defineProps<{
  message: RunMessage
  events: RunEvent[]
  projectName?: string | null
  canRetry?: boolean
  retrying?: boolean
}>()

const emit = defineEmits<{
  retry: []
}>()

const { t } = useI18n()

const provider = computed(() => (props.message.provider === 'cursor' ? 'cursor' : 'claude'))

/** Model name only — no provider prefix, no brackets. */
const modelOnlyLabel = computed(() =>
  modelLabel(props.message.provider as AiProvider | null, props.message.claude_model),
)

const effortLabel = computed(() => {
  if (!props.message.effort) {
    return null
  }
  const key = `runs.chat.effortLevels.${props.message.effort}`
  const translated = t(key)
  if (translated !== key) {
    return translated
  }
  return EFFORT_LABELS[props.message.effort as EffortLevel] ?? props.message.effort
})

const assistantFallback = computed(() => (provider.value === 'cursor' ? t('runs.chat.cursor') : t('runs.chat.claude')))

/**
 * Color class for a streamed log line.
 */
function eventClass(level: string): string {
  if (level === 'error') return 'text-[var(--app-red)]'
  if (level === 'warning') return 'text-[var(--app-blue)]'
  return 'text-[var(--app-ink)]'
}
</script>
