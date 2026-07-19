<template>
  <button
    type="button"
    class="group flex min-h-11 w-full cursor-pointer items-center gap-2 rounded-lg px-1 py-1.5 text-left transition-colors duration-200 hover:bg-[var(--app-surface-2)] focus-visible:ring-2 focus-visible:ring-[var(--app-ink-soft)] focus-visible:outline-none"
    :aria-label="ariaLabel"
    @click="emit('open')"
  >
    <UIcon
      v-if="kind === 'thinking'"
      name="i-lucide-clock"
      class="h-3.5 w-3.5 shrink-0 text-[var(--app-ink-soft)]"
      aria-hidden="true"
    />
    <span class="min-w-0 flex-1 truncate text-sm text-[var(--app-ink-soft)]">
      {{ label }}
      <span v-if="pathHint" class="ml-1 font-mono text-[0.8125rem] text-[var(--app-faint)]">
        {{ pathHint }}
      </span>
    </span>
    <span v-if="showStats" class="inline-flex shrink-0 items-center gap-1.5 font-mono text-xs tabular-nums">
      <span v-if="additions > 0" class="text-[var(--app-green)]">+{{ additions }}</span>
      <span v-if="deletions > 0" class="text-[var(--app-red)]">-{{ deletions }}</span>
    </span>
    <UIcon
      name="i-lucide-chevron-right"
      class="h-4 w-4 shrink-0 text-[var(--app-faint)] transition-transform duration-200 group-hover:translate-x-0.5"
      aria-hidden="true"
    />
  </button>
</template>

<script lang="ts" setup>
import { computed } from 'vue'
import type { ChatActionKind, ChatToolAction } from '~/utils/chatActions'
import { sumDiffStats, truncatePath } from '~/utils/chatActions'

/**
 * Compact Claude-style tool action row (edit / read / bash / thinking).
 */
const props = defineProps<{
  kind: ChatActionKind
  actions: ChatToolAction[]
}>()

const emit = defineEmits<{
  open: []
}>()

const { t } = useI18n()

const stats = computed(() => sumDiffStats(props.actions))
const additions = computed(() => stats.value.additions)
const deletions = computed(() => stats.value.deletions)
const showStats = computed(
  () => (props.kind === 'edit' || props.kind === 'write') && (additions.value > 0 || deletions.value > 0),
)

const fileCount = computed(() => props.actions.length)

const pathHint = computed(() => {
  if (props.kind !== 'read' || props.actions.length !== 1) {
    return ''
  }
  return truncatePath(props.actions[0]?.path || '', 36)
})

const label = computed(() => {
  switch (props.kind) {
    case 'edit':
    case 'write':
      return fileCount.value <= 1
        ? t('runs.chat.review.modifiedOne')
        : t('runs.chat.review.modifiedMany', { n: fileCount.value })
    case 'read':
      return props.actions.length <= 1
        ? t('runs.chat.review.readOne')
        : t('runs.chat.review.readMany', { n: props.actions.length })
    case 'bash':
      return props.actions.length <= 1
        ? t('runs.chat.review.ranOne')
        : t('runs.chat.review.ranMany', { n: props.actions.length })
    case 'thinking':
      return t('runs.chat.review.thinking')
    default:
      return t('runs.chat.review.action')
  }
})

const ariaLabel = computed(() => {
  const parts = [label.value]
  if (pathHint.value) {
    parts.push(pathHint.value)
  }
  if (showStats.value) {
    parts.push(`+${additions.value} -${deletions.value}`)
  }
  return parts.join(' ')
})
</script>
