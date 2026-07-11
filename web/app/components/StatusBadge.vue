<template>
  <span :class="['app-badge whitespace-nowrap', variantClass]">
    <span v-if="dot" :class="['size-1.5 rounded-full', dotClass]" />
    {{ label }}
  </span>
</template>

<script lang="ts" setup>
import { computed } from 'vue'

/**
 * Maps a run / queue / machine status to a themed badge.
 */
const props = withDefaults(
  defineProps<{
    status: string
    dot?: boolean
  }>(),
  { dot: false },
)

const { t } = useI18n()

const SUCCESS = new Set(['COMPLETED', 'DONE', 'IDLE'])
const DANGER = new Set(['FAILED', 'ERROR', 'STOPPED'])
const PROGRESS = new Set(['RUNNING', 'WORKING'])
const INFO = new Set(['WAITING_QUOTA', 'SCHEDULED'])

const variantClass = computed(() => {
  if (SUCCESS.has(props.status)) return 'app-badge--success'
  if (DANGER.has(props.status)) return 'app-badge--danger'
  if (PROGRESS.has(props.status)) return 'app-badge--progress'
  if (INFO.has(props.status)) return 'app-badge--info'
  return ''
})

const dotClass = computed(() => {
  if (SUCCESS.has(props.status)) return 'bg-[var(--app-green)]'
  if (DANGER.has(props.status)) return 'bg-[var(--app-red)]'
  if (PROGRESS.has(props.status)) return 'bg-[var(--app-accent-ink)] animate-pulse'
  if (INFO.has(props.status)) return 'bg-[var(--app-blue)] animate-pulse'
  return 'bg-[var(--app-ink-soft)]'
})

const label = computed(() => {
  const key = `status.${props.status}`
  const translated = t(key)
  return translated !== key ? translated : props.status.replace(/_/g, ' ').toLowerCase()
})
</script>
