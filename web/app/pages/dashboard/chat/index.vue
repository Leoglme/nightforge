<template>
  <div class="flex flex-col gap-5">
    <!-- Header -->
    <header class="flex items-start justify-between gap-3">
      <div class="min-w-0">
        <h1 class="app-page-title">{{ t('nav.chat') }}</h1>
        <p class="text-xs text-[var(--app-ink-soft)] sm:text-sm">{{ t('chat.subtitle') }}</p>
      </div>
      <UButton color="primary" icon="i-lucide-plus" class="hidden shrink-0 sm:inline-flex" @click="openNewConversation">
        {{ t('chat.newConversation') }}
      </UButton>
    </header>

    <!-- Devices strip -->
    <section class="app-card p-3 sm:p-4">
      <div class="mb-2 flex items-center justify-between gap-2">
        <span class="app-label flex items-center gap-1.5">
          <UIcon name="i-lucide-monitor" class="text-[var(--app-accent)]" />
          {{ t('chat.devices') }}
        </span>
        <NuxtLink
          to="/dashboard/machines"
          class="text-xs text-[var(--app-ink-soft)] transition-colors hover:text-[var(--app-ink)]"
        >
          {{ t('chat.manageDevices') }}
        </NuxtLink>
      </div>
      <div v-if="machines.length" class="flex flex-wrap gap-2">
        <span
          v-for="m in machines"
          :key="m.id"
          class="inline-flex items-center gap-1.5 rounded-lg border border-[var(--app-line)] bg-[var(--app-surface-2)] px-2.5 py-1 text-xs font-medium text-[var(--app-ink)]"
        >
          <span :class="['size-1.5 rounded-full', m.online ? 'bg-[var(--app-green)]' : 'bg-[var(--app-ink-soft)]']" />
          {{ m.name }}
          <span class="text-[var(--app-ink-soft)]">{{ m.online ? t('status.ONLINE') : t('status.OFFLINE') }}</span>
        </span>
      </div>
      <p v-else class="text-xs text-[var(--app-ink-soft)]">{{ t('chat.noDevices') }}</p>
    </section>

    <NotificationsToggle />

    <!-- On-PC Claude sessions -->
    <section v-if="pcSessions.length" class="flex min-w-0 flex-col gap-2">
      <span class="app-label flex items-center gap-1.5">
        <UIcon name="i-lucide-laptop" class="text-[var(--app-accent)]" />
        {{ t('chat.pcSessions') }}
      </span>
      <button
        v-for="entry in pcSessions"
        :key="`${entry.machineId}:${entry.session.session_id}`"
        type="button"
        class="group flex items-center gap-3 rounded-xl border border-[var(--app-line)] bg-[var(--app-surface)] px-3 py-3 text-left transition-colors duration-200 hover:border-[var(--app-ink-soft)] hover:bg-[var(--app-surface-2)] sm:px-4"
        @click="openSession(entry)"
      >
        <span
          class="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg border border-[var(--app-line)] bg-[var(--app-bg)] text-[var(--app-ink)]"
        >
          <UIcon
            v-if="isSessionActive(entry)"
            name="i-lucide-loader-circle"
            class="h-4 w-4 animate-spin text-[var(--app-accent-ink)]"
          />
          <ClaudeLogo v-else class="!h-4 !w-4" />
        </span>
        <span class="min-w-0 flex-1">
          <span class="flex items-center justify-between gap-2">
            <span class="truncate text-sm font-medium text-[var(--app-ink)]">{{ sessionTitle(entry.session) }}</span>
            <span class="shrink-0 text-xs text-[var(--app-ink-soft)] tabular-nums">
              {{ formatRelativeFr(entry.session.updated_at) }}
            </span>
          </span>
          <span class="mt-1 flex flex-wrap items-center gap-x-1.5 text-xs text-[var(--app-ink-soft)]">
            <span class="truncate">{{ sessionLocation(entry) }}</span>
            <span v-if="!entry.session.project_id" class="italic opacity-80">
              · {{ t('chat.sessionUnregistered') }}
            </span>
          </span>
        </span>
        <UIcon
          name="i-lucide-play"
          class="h-4 w-4 shrink-0 text-[var(--app-faint)] transition-transform duration-200 group-hover:translate-x-0.5"
          aria-hidden="true"
        />
      </button>
    </section>

    <!-- NightForge conversations -->
    <section class="flex min-w-0 flex-col gap-2">
      <span v-if="pcSessions.length && runs.length" class="app-label flex items-center gap-1.5">
        <UIcon name="i-lucide-messages-square" class="text-[var(--app-accent)]" />
        {{ t('chat.conversations') }}
      </span>

      <div v-if="loading" class="flex justify-center py-10">
        <UIcon name="i-lucide-loader-circle" class="animate-spin text-2xl text-[var(--app-ink-soft)]" />
      </div>

      <div
        v-else-if="!runs.length && !pcSessions.length"
        class="app-card flex flex-col items-center gap-3 px-6 py-12 text-center"
      >
        <UIcon name="i-lucide-messages-square" class="text-3xl text-[var(--app-ink-soft)]" />
        <p class="max-w-sm text-sm text-[var(--app-ink-soft)]">{{ t('chat.emptyHint') }}</p>
        <UButton color="primary" icon="i-lucide-plus" @click="openNewConversation">
          {{ t('chat.newConversation') }}
        </UButton>
      </div>

      <ChatConversationCard v-for="run in runs" v-else :key="run.id" :run="run" :machine="machineFor(run.machine_id)" />
    </section>

    <!-- Floating action button (mobile) -->
    <button
      type="button"
      class="fixed right-4 bottom-[calc(5.75rem+env(safe-area-inset-bottom))] z-30 flex items-center gap-2 rounded-full bg-[var(--app-ink)] px-4 py-3 text-sm font-medium text-[var(--app-surface)] shadow-[var(--app-shadow-soft)] transition-transform duration-200 active:scale-95 sm:hidden"
      @click="openNewConversation"
    >
      <UIcon name="i-lucide-plus" class="h-4 w-4" />
      {{ t('chat.newConversation') }}
    </button>

    <ChatNewConversationDrawer
      :open="newConversationOpen"
      :projects="projects"
      :machines="machines"
      @close="newConversationOpen = false"
      @created="onConversationCreated"
      @create-project="openCreateProject"
    />

    <CreateProjectDrawer
      :open="createProjectOpen"
      :machine-id="firstOnlineMachineId"
      :machine-name="firstOnlineMachineName"
      show-back
      @back="backToNewConversation"
      @close="createProjectOpen = false"
      @created="onProjectCreated"
    />
  </div>
</template>

<script lang="ts" setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import type { ClaudeSession, Machine, Project, Run } from '~/types'
import { formatRelativeFr } from '~/utils/datetime'
import { listClaudeSessions, listMachines } from '~/services/machinesService'
import { listProjects } from '~/services/projectsService'
import { listRuns } from '~/services/runsService'

/** A Claude session found on a machine, tagged with which machine it lives on. */
type PcSession = { session: ClaudeSession; machineId: number; machineName: string }

/**
 * Discussions hub — the conversation-first entry point (start / resume Claude Code
 * and Cursor conversations remotely, then review the AI's changes on any device).
 */
definePageMeta({ layout: 'dashboard', middleware: 'auth' })

const { t } = useI18n()
const router = useRouter()
const activity = useSessionActivityStore()

const runs = ref<Run[]>([])
const machines = ref<Machine[]>([])
const projects = ref<Project[]>([])
const pcSessions = ref<PcSession[]>([])
const loading = ref(true)
const newConversationOpen = ref(false)
const createProjectOpen = ref(false)
let timer: ReturnType<typeof setInterval> | null = null
let sessionsTimer: ReturnType<typeof setInterval> | null = null

const firstOnlineMachineId = computed(() => (machines.value.find((m) => m.online) ?? machines.value[0])?.id)
const firstOnlineMachineName = computed(() => (machines.value.find((m) => m.online) ?? machines.value[0])?.name)

/**
 * Resolve the machine a run targets (for the conversation card).
 * @param machineId - The run's machine id.
 * @returns The machine or null.
 */
function machineFor(machineId: number): Machine | null {
  return machines.value.find((m) => m.id === machineId) ?? null
}

/**
 * Display title for an on-PC session.
 * @param session - The Claude session.
 * @returns The custom title or a short id fallback.
 */
function sessionTitle(session: ClaudeSession): string {
  return session.title || t('chat.sessionShort', { id: session.session_id.slice(0, 8) })
}

/**
 * Secondary line for an on-PC session: project name (or folder) + machine.
 * @param entry - The tagged session.
 * @returns The location label.
 */
function sessionLocation(entry: PcSession): string {
  const folder = entry.session.cwd?.split(/[\\/]/).filter(Boolean).pop()
  const where = entry.session.project_name || folder || '—'
  return `${where} · ${entry.machineName}`
}

/**
 * Whether a session is currently working — live WebSocket feed first, poll as fallback.
 * @param entry - The tagged session.
 * @returns True while active.
 */
function isSessionActive(entry: PcSession): boolean {
  return activity.isActive(entry.session.session_id) || Boolean(entry.session.is_running)
}

/**
 * Open the new-conversation drawer.
 * @returns Nothing.
 */
function openNewConversation(): void {
  newConversationOpen.value = true
}

/**
 * Open an on-PC session directly in its chat view (history + continue).
 * @param entry - The tagged session to open.
 * @returns Nothing.
 */
function openSession(entry: PcSession): void {
  router.push(`/dashboard/chat/pc/${entry.machineId}/${entry.session.session_id}`)
}

/**
 * Switch from the conversation drawer to the create-project drawer.
 * @returns Nothing.
 */
function openCreateProject(): void {
  newConversationOpen.value = false
  createProjectOpen.value = true
}

/**
 * Go back from create-project to the conversation drawer.
 * @returns Nothing.
 */
function backToNewConversation(): void {
  createProjectOpen.value = false
  newConversationOpen.value = true
}

/**
 * After creating a project, refresh the list and reopen the conversation drawer.
 * @param project - The newly created project.
 * @returns Nothing.
 */
async function onProjectCreated(project: Project): Promise<void> {
  const fresh = await listProjects().catch(() => null)
  projects.value = fresh ?? [...projects.value, project]
  createProjectOpen.value = false
  newConversationOpen.value = true
}

/**
 * Navigate to the freshly started conversation.
 * @param run - The created run.
 * @returns Nothing.
 */
function onConversationCreated(run: Run): void {
  newConversationOpen.value = false
  router.push(`/dashboard/chat/${run.id}`)
}

/**
 * Refresh conversations and machine status.
 * @returns Nothing.
 */
async function refresh(): Promise<void> {
  const [freshRuns, freshMachines] = await Promise.all([
    listRuns().catch(() => runs.value),
    listMachines().catch(() => machines.value),
  ])
  runs.value = freshRuns
  machines.value = freshMachines
}

/**
 * Refresh the on-PC Claude sessions of every online machine.
 * @returns Nothing.
 */
async function refreshSessions(): Promise<void> {
  const online = machines.value.filter((m) => m.online)
  if (!online.length) {
    pcSessions.value = []
    return
  }
  const perMachine = await Promise.all(
    online.map(async (machine): Promise<PcSession[] | null> => {
      const response = await listClaudeSessions(machine.id).catch(() => null)
      return response
        ? response.sessions.map((session) => ({ session, machineId: machine.id, machineName: machine.name }))
        : null
    }),
  )
  const succeeded = perMachine.filter((result): result is PcSession[] => result !== null)
  // All fetches failed transiently — keep the current list rather than flashing empty.
  if (!succeeded.length && pcSessions.value.length) {
    return
  }
  pcSessions.value = succeeded.flat().sort((a, b) => b.session.updated_at.localeCompare(a.session.updated_at))
}

onMounted(async () => {
  projects.value = await listProjects().catch(() => [])
  await refresh()
  await refreshSessions()
  loading.value = false
  timer = setInterval(refresh, 8000)
  // Slower now that the live spinner comes from the WebSocket; this just refreshes the list.
  sessionsTimer = setInterval(refreshSessions, 12000)
})

onBeforeUnmount(() => {
  if (timer) clearInterval(timer)
  if (sessionsTimer) clearInterval(sessionsTimer)
})
</script>
