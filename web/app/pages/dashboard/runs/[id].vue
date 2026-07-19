<template>
  <div class="flex min-h-0 flex-1 flex-col bg-[var(--app-bg)]">
    <!-- Top bar: title | meta (center) | actions — single compact row -->
    <header
      class="flex shrink-0 items-center gap-2 border-b border-[var(--app-line)] bg-[var(--app-surface)] px-3 py-2 sm:gap-3 sm:px-5 sm:py-2.5"
    >
      <div class="flex min-w-0 shrink-0 items-center gap-2">
        <UButton
          size="sm"
          color="neutral"
          variant="ghost"
          icon="i-lucide-arrow-left"
          to="/dashboard/runs"
          :aria-label="t('nav.back')"
        />
        <h1 class="truncate text-base font-semibold tracking-[-0.02em] text-[var(--app-ink)] sm:text-lg">
          {{ isQuick ? t('common.launch') : t('common.night') }} #{{ id }}
        </h1>
      </div>

      <p
        v-if="headerMeta"
        class="hidden min-w-0 flex-1 truncate text-center text-xs text-[var(--app-ink-soft)] sm:block"
      >
        {{ headerMeta }}
      </p>

      <div class="ml-auto flex shrink-0 items-center gap-2">
        <StatusBadge v-if="run" :status="run.status" dot />
        <UButton v-if="run && isActive" size="sm" color="error" variant="outline" icon="i-lucide-square" @click="stop">
          <span class="hidden sm:inline">{{ t('common.stop') }}</span>
        </UButton>
      </div>
    </header>

    <!-- Night-only: compact quota plan (no card grid clutter) -->
    <div
      v-if="run && !isQuick && quotaPlan?.windows?.length"
      class="shrink-0 border-b border-[var(--app-line)] bg-[var(--app-surface)] px-3 py-2 sm:px-5"
    >
      <div class="flex flex-wrap items-center justify-between gap-2">
        <p class="text-xs text-[var(--app-ink-soft)]">
          <span class="app-label mr-2">{{ t('runs.chat.quotaPlan') }}</span>
          {{ run.quota_count }} ·
          {{ run.parallel ? t('common.parallel') : t('common.sequential') }}
          <span v-if="quotaPlan.fresh_quota_available_at" class="ml-1">
            · {{ t('runs.chat.freshAt') }} {{ formatTimeFr(quotaPlan.fresh_quota_available_at) }}
          </span>
        </p>
        <div v-if="isActive" class="flex gap-1">
          <UButton size="xs" color="neutral" variant="outline" :loading="addingQuota" @click="addQuota(1)">
            +1
          </UButton>
          <UButton size="xs" color="neutral" variant="outline" :loading="addingQuota" @click="addQuota(2)">
            +2
          </UButton>
        </div>
      </div>
    </div>

    <!-- Chat thread -->
    <div
      ref="threadEl"
      class="min-h-0 flex-1 space-y-8 overflow-y-auto overscroll-contain px-3 py-4 sm:space-y-10 sm:px-5 sm:py-6"
    >
      <div
        v-if="!messages.length"
        class="mx-auto flex max-w-md flex-col items-center gap-2 rounded-2xl border border-dashed border-[var(--app-line)] px-4 py-10 text-center sm:px-6 sm:py-12"
      >
        <UIcon name="i-lucide-messages-square" class="h-7 w-7 text-[var(--app-ink-soft)]" />
        <p class="text-sm font-medium text-[var(--app-ink)]">{{ t('runs.chat.emptyTitle') }}</p>
        <p class="text-xs text-[var(--app-ink-soft)]">{{ t('runs.chat.emptyHint') }}</p>
      </div>

      <RunChatTurn
        v-for="turn in turns"
        :key="turn.message.id"
        :message="turn.message"
        :events="turn.events"
        :project-name="projectNameFor(turn.message.project_id)"
        :can-retry="canRetryMessage(turn.message)"
        :retrying="retryingId === turn.message.id"
        @retry="retryMessage(turn.message)"
      />
    </div>

    <!-- Composer -->
    <footer
      v-if="run && canAddMessage"
      class="shrink-0 border-t border-[var(--app-line)] bg-[var(--app-surface)] px-3 pt-3 pb-[max(0.75rem,env(safe-area-inset-bottom))] sm:px-5 sm:pt-3.5 sm:pb-4"
    >
      <RunChatComposer
        v-model:text="newMessageText"
        v-model:provider="selectedProvider"
        v-model:model="selectedModel"
        v-model:effort="selectedEffort"
        v-model:fast-mode="selectedFast"
        :project-id="newMessageProjectId"
        :project-options="runProjectOptions"
        :can-send="canSubmitMessage"
        :loading="addingMessage"
        @update:project-id="newMessageProjectId = $event"
        @send="addMessage"
      />
    </footer>
  </div>
</template>

<script lang="ts" setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import type { Machine, QuotaPlan, Run, RunEvent, RunMessage } from '~/types'
import type { AiProvider } from '~/constants/modelPresets'
import { formatTimeFr } from '~/utils/datetime'
import { planQuota } from '~/services/quotaService'
import { listMachines } from '~/services/machinesService'
import {
  addRunMessage,
  addRunQuotas,
  continueRunMessage,
  getRun,
  listRunEvents,
  listRunMessages,
  listRunProjects,
  stopRun,
} from '~/services/runsService'
import type { RunProjectSummary } from '~/services/runsService'

/**
 * Run detail — chat-style launch view (prompts + streamed agent output).
 */
definePageMeta({ layout: 'dashboard', middleware: 'auth' })

const { t } = useI18n()
const route = useRoute()
const toast = useToast()
const id = Number(route.params.id)

const run = ref<Run | null>(null)
const livePlan = ref<QuotaPlan | null>(null)
const events = ref<RunEvent[]>([])
const messages = ref<RunMessage[]>([])
const threadEl = ref<HTMLElement | null>(null)
const retryingId = ref<number | null>(null)
const addingQuota = ref(false)
const addingMessage = ref(false)
const runProjects = ref<RunProjectSummary[]>([])
const machines = ref<Machine[]>([])
const newMessageText = ref('')
const newMessageProjectId = ref<number | undefined>(undefined)
const selectedModel = ref<string | null>('composer-2.5')
const selectedProvider = ref<AiProvider | null>('cursor')
const selectedEffort = ref<string | null>(null)
const selectedFast = ref(false)
const prefsInitialized = ref(false)
let lastId = 0
let timer: ReturnType<typeof setInterval> | null = null

const ACTIVE_STATUSES = new Set(['SCHEDULED', 'RUNNING', 'WAITING_QUOTA'])

const isActive = computed(() => (run.value ? ACTIVE_STATUSES.has(run.value.status) : false))
const isQuick = computed(() => (run.value?.kind ?? 'night') === 'quick')
const doneCount = computed(() => messages.value.filter((m) => m.status === 'DONE').length)

const machineName = computed(() => {
  const machine = machines.value.find((m) => m.id === run.value?.machine_id)
  return machine?.name ?? (run.value ? `#${run.value.machine_id}` : '')
})

const projectSummary = computed(() => {
  if (!runProjects.value.length) {
    return ''
  }
  return runProjects.value.map((p) => p.name).join(' · ')
})

/** Compact meta for the header center (project · machine · progress). */
const headerMeta = computed(() => {
  const parts: string[] = []
  if (projectSummary.value) {
    parts.push(projectSummary.value)
  }
  if (machineName.value) {
    parts.push(machineName.value)
  }
  if (messages.value.length) {
    parts.push(`${doneCount.value} / ${messages.value.length}`)
  }
  return parts.join(' · ')
})

const canAddMessage = computed(() => {
  if (!run.value) {
    return false
  }
  // Active runs always accept follow-ups. Quick launches also keep the composer
  // after terminal status — the API reopens the run on the next send.
  if (isActive.value || isQuick.value) {
    return true
  }
  return false
})

const runProjectOptions = computed(() => runProjects.value.map((p) => ({ label: p.name, value: p.project_id })))

const resolvedProjectId = computed(() => {
  if (newMessageProjectId.value) {
    return newMessageProjectId.value
  }
  if (runProjects.value.length === 1) {
    return runProjects.value[0]!.project_id
  }
  const last = messages.value[messages.value.length - 1]
  return last?.project_id
})

const canSubmitMessage = computed(() => Boolean(newMessageText.value.trim() && resolvedProjectId.value))

const quotaPlan = computed(() => {
  if (isQuick.value) {
    return null
  }
  if (run.value && ACTIVE_STATUSES.has(run.value.status) && livePlan.value) {
    return livePlan.value
  }
  return run.value?.planned_timeline ?? null
})

/**
 * Pair each user message with the agent events that belong to that turn
 * (by created_at window between this message and the next).
 */
const turns = computed(() => {
  const sorted = [...messages.value].sort((a, b) => {
    if (a.order_index !== b.order_index) {
      return a.order_index - b.order_index
    }
    return a.id - b.id
  })
  const sortedEvents = [...events.value].sort(
    (a, b) => new Date(a.created_at).getTime() - new Date(b.created_at).getTime(),
  )

  return sorted.map((message, index) => {
    const start = index === 0 ? Number.NEGATIVE_INFINITY : new Date(message.created_at).getTime()
    const next = sorted[index + 1]
    const end = next ? new Date(next.created_at).getTime() : Number.POSITIVE_INFINITY
    const turnEvents = sortedEvents.filter((ev) => {
      const ts = new Date(ev.created_at).getTime()
      return ts >= start && ts < end
    })
    return { message, events: turnEvents }
  })
})

/**
 * Resolve a project display name for a message.
 */
function projectNameFor(projectId: number): string | null {
  if (runProjects.value.length <= 1) {
    return null
  }
  return runProjects.value.find((p) => p.project_id === projectId)?.name ?? null
}

/**
 * Seed composer prefs from the latest message once.
 */
function syncComposerFromMessages(): void {
  if (prefsInitialized.value || !messages.value.length) {
    return
  }
  const last = messages.value[messages.value.length - 1]!
  if (last.provider === 'claude' || last.provider === 'cursor') {
    selectedProvider.value = last.provider
  }
  if (last.claude_model) {
    selectedModel.value = last.claude_model
  }
  selectedEffort.value = last.effort ?? null
  selectedFast.value = Boolean(last.fast_mode)
  prefsInitialized.value = true
}

/**
 * Scroll the chat thread to the bottom after new content.
 */
async function scrollThread(): Promise<void> {
  await nextTick()
  if (threadEl.value) {
    threadEl.value.scrollTop = threadEl.value.scrollHeight
  }
}

async function poll(): Promise<void> {
  const prevEventCount = events.value.length
  const prevMessageCount = messages.value.length

  run.value = await getRun(id).catch(() => run.value)
  if (run.value && !isQuick.value && ACTIVE_STATUSES.has(run.value.status)) {
    livePlan.value = await planQuota({
      quota_count: run.value.quota_count,
      machine_id: run.value.machine_id,
      start_at: run.value.started_at ?? undefined,
    }).catch(() => livePlan.value)
  }
  messages.value = await listRunMessages(id).catch(() => messages.value)
  syncComposerFromMessages()
  await loadRunProjects()
  const fresh = await listRunEvents(id, lastId).catch(() => [])
  if (fresh.length > 0) {
    events.value.push(...fresh)
    lastId = fresh[fresh.length - 1]!.id
  }

  if (events.value.length !== prevEventCount || messages.value.length !== prevMessageCount) {
    await scrollThread()
  }
}

async function stop(): Promise<void> {
  await stopRun(id)
  await poll()
}

function canRetryMessage(message: RunMessage): boolean {
  if (message.status === 'RUNNING') {
    return false
  }
  if (isActive.value) {
    return true
  }
  // Finished run with stuck PENDING/FAILED — retry reopens the run via the API.
  return message.status === 'PENDING' || message.status === 'FAILED' || message.status === 'SKIPPED'
}

async function retryMessage(message: RunMessage): Promise<void> {
  retryingId.value = message.id
  try {
    await continueRunMessage(id, message)
    await poll()
  } finally {
    retryingId.value = null
  }
}

async function addQuota(count: number): Promise<void> {
  addingQuota.value = true
  try {
    run.value = await addRunQuotas(id, count)
    if (run.value && ACTIVE_STATUSES.has(run.value.status)) {
      livePlan.value = await planQuota({
        quota_count: run.value.quota_count,
        machine_id: run.value.machine_id,
        start_at: run.value.started_at ?? undefined,
      })
    }
  } finally {
    addingQuota.value = false
  }
}

async function loadRunProjects(): Promise<void> {
  const projects = await listRunProjects(id).catch(() => runProjects.value)
  if (projects.length > 0) {
    runProjects.value = projects
  }
  if (!newMessageProjectId.value) {
    if (projects.length === 1) {
      newMessageProjectId.value = projects[0]!.project_id
    } else if (messages.value.length > 0) {
      newMessageProjectId.value = messages.value[messages.value.length - 1]!.project_id
    }
  }
}

async function addMessage(): Promise<void> {
  const content = newMessageText.value.trim()
  const projectId = resolvedProjectId.value
  if (!content || !projectId) {
    return
  }
  addingMessage.value = true
  try {
    const created = await addRunMessage(id, {
      project_id: projectId,
      content,
      claude_model: selectedModel.value,
      provider: selectedProvider.value,
      effort: selectedEffort.value,
      fast_mode: selectedFast.value,
    })
    messages.value = [...messages.value, created]
    newMessageText.value = ''
    await poll()
    await scrollThread()
    toast.add({ title: t('runs.chat.sent'), color: 'success' })
  } catch (err) {
    toast.add({
      title: t('runs.chat.sendFailed'),
      description: err instanceof Error ? err.message : undefined,
      color: 'error',
    })
  } finally {
    addingMessage.value = false
  }
}

onMounted(() => {
  listMachines()
    .then((list) => {
      machines.value = list
    })
    .catch(() => {})
  poll()
  timer = setInterval(poll, 3000)
})

onBeforeUnmount(() => {
  if (timer) clearInterval(timer)
})
</script>
