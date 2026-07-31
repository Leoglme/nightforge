<template>
  <NuxtLink
    :to="`/dashboard/chat/${run.id}`"
    class="group flex items-center gap-3 rounded-xl border border-[var(--app-line)] bg-[var(--app-surface)] px-3 py-3 transition-colors duration-200 hover:border-[var(--app-ink-soft)] hover:bg-[var(--app-surface-2)] sm:px-4"
  >
    <!-- Icon + live indicator -->
    <span
      class="relative flex h-10 w-10 shrink-0 items-center justify-center rounded-lg border border-[var(--app-line)] bg-[var(--app-bg)] text-[var(--app-ink)]"
    >
      <UIcon :name="isNight ? 'i-lucide-moon-star' : 'i-lucide-messages-square'" class="h-4 w-4" />
      <span
        v-if="showLiveDot"
        class="absolute -top-0.5 -right-0.5 h-2.5 w-2.5 animate-pulse rounded-full border-2 border-[var(--app-surface)] bg-[var(--app-blue)]"
        aria-hidden="true"
      />
    </span>

    <span class="min-w-0 flex-1">
      <span class="flex items-center justify-between gap-2">
        <span class="truncate text-sm font-medium text-[var(--app-ink)]">{{ title }}</span>
        <span class="shrink-0 text-xs text-[var(--app-ink-soft)] tabular-nums">{{ timeLabel }}</span>
      </span>
      <span class="mt-1.5 flex flex-wrap items-center gap-x-1.5 gap-y-1 text-xs text-[var(--app-ink-soft)]">
        <StatusBadge :status="run.status" dot />
        <span
          v-if="isNight"
          class="rounded bg-[var(--app-surface-2)] px-1.5 py-0.5 text-[10px] font-medium text-[var(--app-ink-soft)]"
        >
          {{ t('common.night') }}
        </span>
        <span v-if="subtitle" class="min-w-0 truncate">· {{ subtitle }}</span>
        <span v-if="offline" class="text-[var(--app-red)]">· {{ t('chat.machineOffline') }}</span>
      </span>
    </span>

    <UIcon
      name="i-lucide-chevron-right"
      class="h-4 w-4 shrink-0 text-[var(--app-faint)] transition-transform duration-200 group-hover:translate-x-0.5"
      aria-hidden="true"
    />
  </NuxtLink>
</template>

<script lang="ts" setup>
import { computed } from 'vue'
import type { Machine, Run } from '~/types'
import { formatRelativeFr } from '~/utils/datetime'

/**
 * One conversation row in the Discussions hub — Claude-Code-mobile style.
 */
const props = defineProps<{
  run: Run
  machine?: Machine | null
}>()

const { t } = useI18n()

const ACTIVE_STATUSES = new Set(['SCHEDULED', 'RUNNING', 'WAITING_QUOTA'])

const isActive = computed(() => ACTIVE_STATUSES.has(props.run.status))
const isNight = computed(() => (props.run.kind ?? 'night') === 'night')

const online = computed(() => Boolean(props.machine?.online))

/** Active conversation on an offline machine — nothing can execute right now. */
const offline = computed(() => isActive.value && !online.value)

/** Pulse the live dot only when the conversation can actually run. */
const showLiveDot = computed(() => isActive.value && online.value)

/** Title: the first user message, else a project/id fallback. */
const title = computed(() => {
  if (props.run.title) {
    return props.run.title
  }
  if (props.run.project_names?.length) {
    return props.run.project_names.join(' · ')
  }
  return `${isNight.value ? t('common.night') : t('common.launch')} #${props.run.id}`
})

/** Secondary line: project names then machine name. */
const subtitle = computed(() => {
  const parts: string[] = []
  if (props.run.project_names?.length) {
    parts.push(props.run.project_names.join(' · '))
  }
  if (props.machine?.name) {
    parts.push(props.machine.name)
  }
  return parts.join(' · ')
})

const timeLabel = computed(() => formatRelativeFr(props.run.last_activity_at || props.run.created_at))
</script>
