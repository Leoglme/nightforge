<template>
  <div class="flex flex-col gap-6">
    <div class="flex items-center justify-between gap-3">
      <div class="flex items-center gap-3">
        <UButton size="sm" color="neutral" variant="ghost" icon="i-lucide-arrow-left" to="/dashboard/runs" />
        <h1 class="app-page-title">{{ t('common.night') }} #{{ id }}</h1>
        <StatusBadge v-if="run" :status="run.status" dot />
      </div>
      <UButton
        v-if="run && ['SCHEDULED', 'RUNNING', 'WAITING_QUOTA'].includes(run.status)"
        size="sm"
        color="error"
        variant="outline"
        icon="i-lucide-square"
        @click="stop"
      >
        {{ t('common.stop') }}
      </UButton>
    </div>

    <div v-if="run" class="grid grid-cols-2 gap-4 sm:grid-cols-4">
      <UCard>
        <div class="app-label">{{ t('common.machine') }}</div>
        <div class="mt-1 font-medium">#{{ run.machine_id }}</div>
      </UCard>
      <UCard>
        <div class="app-label">{{ t('common.quotas') }}</div>
        <div class="mt-1 font-medium">{{ run.quota_count }}</div>
      </UCard>
      <UCard>
        <div class="app-label">{{ t('common.mode') }}</div>
        <div class="mt-1 font-medium">{{ run.parallel ? t('common.parallel') : t('common.sequential') }}</div>
      </UCard>
      <UCard>
        <div class="app-label">{{ t('common.started') }}</div>
        <div class="mt-1 text-sm">{{ run.started_at ? formatDateTimeFr(run.started_at) : '—' }}</div>
      </UCard>
    </div>

    <UCard v-if="quotaPlan?.windows?.length">
      <template #header>
        <div class="flex items-center justify-between gap-2">
          <span class="app-label">Plan de quotas</span>
          <div v-if="run && isActive" class="flex gap-1">
            <UButton size="xs" color="neutral" variant="outline" :loading="addingQuota" @click="addQuota(1)">
              +1 quota
            </UButton>
            <UButton size="xs" color="neutral" variant="outline" :loading="addingQuota" @click="addQuota(2)">
              +2
            </UButton>
          </div>
        </div>
      </template>
      <ul class="flex flex-col gap-2 text-sm">
        <li v-for="w in quotaPlan.windows" :key="w.index" class="flex items-center justify-between gap-2">
          <span>Quota #{{ w.index }}</span>
          <span class="text-right text-[var(--app-ink-soft)]">
            {{ formatTimeFr(w.starts_at) }} → {{ t('common.reset') }} {{ formatTimeFr(w.resets_at) }}
            <span
              v-if="w.index === 1"
              class="ml-1 rounded px-1 py-0.5 text-[0.65rem] font-medium"
              :class="
                w.estimated
                  ? 'bg-[var(--app-surface-2)] text-[var(--app-ink-soft)]'
                  : 'bg-[var(--app-accent-soft)] text-[var(--app-accent-ink)]'
              "
            >
              {{ w.estimated ? t('common.estimated') : t('common.real') }}
            </span>
          </span>
        </li>
        <li class="flex items-center justify-between border-t border-[var(--app-line)] pt-2 font-medium">
          <span>Quota vierge dispo</span>
          <span>{{ formatTimeFr(quotaPlan.fresh_quota_available_at) }}</span>
        </li>
      </ul>
    </UCard>

    <UCard>
      <template #header>
        <div class="flex items-center justify-between">
          <span class="app-label">Séquence de messages</span>
          <span class="text-xs text-[var(--app-ink-soft)]">{{ doneCount }} / {{ messages.length }}</span>
        </div>
      </template>
      <ul v-if="messages.length" class="flex flex-col gap-2">
        <li
          v-for="(message, index) in messages"
          :key="message.id"
          class="flex items-start gap-3 rounded-lg border border-[var(--app-line)] px-3 py-2 text-sm"
        >
          <div class="min-w-0 flex-1">
            <div class="flex flex-wrap items-center gap-2">
              <div class="app-label">Message {{ index + 1 }}</div>
              <span
                v-if="message.claude_session_id"
                class="rounded bg-[var(--app-surface-2)] px-1.5 py-0.5 text-[0.6rem] text-[var(--app-ink-soft)]"
                :title="message.claude_session_id"
              >
                session
              </span>
              <span
                v-if="message.claude_model"
                class="rounded bg-[var(--app-accent-soft)] px-1.5 py-0.5 text-[0.6rem] text-[var(--app-accent-ink)]"
              >
                {{ claudeModelLabel(message.claude_model) }}
              </span>
            </div>
            <p class="mt-0.5 break-words whitespace-pre-wrap text-[var(--app-ink-soft)]">
              {{ message.content }}
            </p>
          </div>
          <div class="flex shrink-0 flex-col items-end gap-1.5 self-start">
            <StatusBadge :status="message.status" dot class="whitespace-nowrap" />
            <UButton
              v-if="canRetryMessage(message)"
              size="xs"
              color="neutral"
              variant="outline"
              icon="i-lucide-rotate-ccw"
              :loading="retryingId === message.id"
              @click="retryMessage(message)"
            >
              Relancer
            </UButton>
          </div>
        </li>
      </ul>
      <p v-else class="text-sm text-[var(--app-ink-soft)]">Aucun message pour l'instant.</p>

      <div v-if="run && canAddMessage" class="mt-4 border-t border-[var(--app-line)] pt-4">
        <p class="app-label mb-2">Ajouter un message</p>
        <UFormField v-if="runProjects.length > 1" label="Projet" class="mb-2">
          <USelectMenu
            v-model="newMessageProjectId"
            :items="runProjectOptions"
            value-key="value"
            label-key="label"
            class="w-full"
          />
        </UFormField>

        <div class="mb-3 grid gap-3 sm:grid-cols-2">
          <ComposerSessionPicker
            v-model="selectedSessionId"
            :machine-id="run?.machine_id"
            :local-path="activeLocalPath"
            :offline="!machineOnline"
          />
          <ComposerModelPicker v-model="selectedModel" />
        </div>

        <UTextarea
          v-model="newMessageText"
          :rows="3"
          autoresize
          placeholder="Nouveau prompt pour Claude Code…"
          class="mb-2 w-full"
          @keydown.enter.exact.prevent="addMessage"
        />
        <div class="flex flex-wrap items-center justify-end gap-2">
          <UButton
            size="sm"
            color="primary"
            icon="i-lucide-plus"
            :disabled="!canSubmitMessage"
            :loading="addingMessage"
            @click="addMessage"
          >
            Ajouter à la séquence
          </UButton>
        </div>
      </div>
    </UCard>

    <UCard>
      <template #header>
        <div class="flex items-center justify-between">
          <span class="app-label">Logs live</span>
          <span class="text-xs text-[var(--app-ink-soft)]">{{ events.length }} lignes</span>
        </div>
      </template>
      <div
        ref="logBox"
        class="max-h-[50vh] overflow-y-auto rounded-md bg-[var(--app-surface-2)] p-3 text-xs leading-relaxed font-[var(--app-font-mono)]"
      >
        <div v-if="events.length === 0" class="text-[var(--app-ink-soft)]">En attente de logs…</div>
        <div v-for="ev in events" :key="ev.id" :class="['whitespace-pre-wrap', levelClass(ev.level)]">
          <span class="text-[var(--app-ink-soft)]">{{ formatClockFr(ev.created_at) }}</span>
          {{ ev.message }}
        </div>
      </div>
    </UCard>
  </div>
</template>

<script lang="ts" setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import type { Machine, QuotaPlan, Run, RunEvent, RunMessage } from '~/types'
import { claudeModelLabel } from '~/constants/claudeModels'
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
 * Run detail page with live-polled logs, quota plan and kill switch.
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
const logBox = ref<HTMLElement | null>(null)
const retryingId = ref<number | null>(null)
const addingQuota = ref(false)
const addingMessage = ref(false)
const runProjects = ref<RunProjectSummary[]>([])
const machines = ref<Machine[]>([])
const newMessageText = ref('')
const newMessageProjectId = ref<number | undefined>(undefined)
const selectedSessionId = ref<string | null>(null)
const selectedModel = ref<string | null>(null)
const sessionInitialized = ref(false)
let lastId = 0
let timer: ReturnType<typeof setInterval> | null = null

const ACTIVE_STATUSES = new Set(['SCHEDULED', 'RUNNING', 'WAITING_QUOTA'])

const isActive = computed(() => (run.value ? ACTIVE_STATUSES.has(run.value.status) : false))

const doneCount = computed(() => messages.value.filter((m) => m.status === 'DONE').length)

const canAddMessage = computed(() => isActive.value)

const runProjectOptions = computed(() => runProjects.value.map((p) => ({ label: p.name, value: p.project_id })))

const machineOnline = computed(() => machines.value.find((m) => m.id === run.value?.machine_id)?.online ?? false)

const activeLocalPath = computed(() => {
  const projectId = resolvedProjectId.value
  if (!projectId) {
    return null
  }
  const project = runProjects.value.find((p) => p.project_id === projectId)
  return project?.local_path?.trim() || null
})

const lastSessionId = computed(() => {
  for (let i = messages.value.length - 1; i >= 0; i -= 1) {
    const id = messages.value[i]?.claude_session_id
    if (id) {
      return id
    }
  }
  return null
})

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

/** Live plan (anchored on real reset) while the night is active; frozen snapshot otherwise. */
const quotaPlan = computed(() => {
  if (run.value && ACTIVE_STATUSES.has(run.value.status) && livePlan.value) {
    return livePlan.value
  }
  return run.value?.planned_timeline ?? null
})

/**
 * Poll the run status, its message progress and any new log events.
 * @returns Nothing.
 */
async function poll(): Promise<void> {
  run.value = await getRun(id).catch(() => run.value)
  if (run.value && ACTIVE_STATUSES.has(run.value.status)) {
    livePlan.value = await planQuota({
      quota_count: run.value.quota_count,
      machine_id: run.value.machine_id,
      start_at: run.value.started_at ?? undefined,
    }).catch(() => livePlan.value)
  }
  messages.value = await listRunMessages(id).catch(() => messages.value)
  await loadRunProjects()
  const fresh = await listRunEvents(id, lastId).catch(() => [])
  if (fresh.length > 0) {
    events.value.push(...fresh)
    lastId = fresh[fresh.length - 1]!.id
    await nextTick()
    if (logBox.value) logBox.value.scrollTop = logBox.value.scrollHeight
  }
}

/**
 * Stop this run.
 * @returns Nothing.
 */
async function stop(): Promise<void> {
  await stopRun(id)
  await poll()
}

/**
 * Whether a message can be re-queued for execution.
 * @param message - The run message.
 * @returns True when retry is allowed.
 */
function canRetryMessage(message: RunMessage): boolean {
  return message.status !== 'RUNNING'
}

/**
 * Re-queue a message (sends « Vas-y continue » when a session is linked).
 * @param message - The message to retry.
 * @returns Nothing.
 */
async function retryMessage(message: RunMessage): Promise<void> {
  retryingId.value = message.id
  try {
    await continueRunMessage(id, message)
    await poll()
  } finally {
    retryingId.value = null
  }
}

/**
 * Extend the quota budget without stopping the night.
 * @param count - Quotas to add.
 * @returns Nothing.
 */
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

/**
 * Load projects for this run and pre-select when unambiguous.
 * @returns Nothing.
 */
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

/**
 * Append a new message to the run sequence.
 * @returns Nothing.
 */
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
      claude_session_id: selectedSessionId.value,
      claude_model: selectedModel.value,
    })
    messages.value = [...messages.value, created]
    newMessageText.value = ''
    selectedSessionId.value = null
    await poll()
    toast.add({ title: 'Message ajouté à la séquence', color: 'success' })
  } catch (err) {
    toast.add({
      title: "Impossible d'ajouter le message",
      description: err instanceof Error ? err.message : undefined,
      color: 'error',
    })
  } finally {
    addingMessage.value = false
  }
}

/**
 * Map a log level to a text color class.
 * @param level - The log level.
 * @returns A CSS class.
 */
function levelClass(level: string): string {
  if (level === 'error') return 'text-[var(--app-red)]'
  if (level === 'warning') return 'text-[var(--app-blue)]'
  return 'text-[var(--app-ink)]'
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

watch(
  lastSessionId,
  (sessionId) => {
    if (!sessionInitialized.value && sessionId) {
      selectedSessionId.value = sessionId
      sessionInitialized.value = true
    }
  },
  { immediate: true },
)

onBeforeUnmount(() => {
  if (timer) clearInterval(timer)
})
</script>
