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

    <!-- Conversations -->
    <section class="flex min-w-0 flex-col gap-2">
      <div v-if="loading" class="flex justify-center py-10">
        <UIcon name="i-lucide-loader-circle" class="animate-spin text-2xl text-[var(--app-ink-soft)]" />
      </div>

      <div v-else-if="!runs.length" class="app-card flex flex-col items-center gap-3 px-6 py-12 text-center">
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
      class="fixed right-4 bottom-[calc(4.75rem+env(safe-area-inset-bottom))] z-30 flex items-center gap-2 rounded-full bg-[var(--app-ink)] px-4 py-3 text-sm font-medium text-[var(--app-surface)] shadow-[var(--app-shadow-soft)] transition-transform duration-200 active:scale-95 sm:hidden"
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
import type { Machine, Project, Run } from '~/types'
import { listMachines } from '~/services/machinesService'
import { listProjects } from '~/services/projectsService'
import { listRuns } from '~/services/runsService'

/**
 * Discussions hub — the conversation-first entry point (start / resume Claude Code
 * and Cursor conversations remotely, then review the AI's changes on any device).
 */
definePageMeta({ layout: 'dashboard', middleware: 'auth' })

const { t } = useI18n()
const router = useRouter()

const runs = ref<Run[]>([])
const machines = ref<Machine[]>([])
const projects = ref<Project[]>([])
const loading = ref(true)
const newConversationOpen = ref(false)
const createProjectOpen = ref(false)
let timer: ReturnType<typeof setInterval> | null = null

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
 * Open the new-conversation drawer.
 * @returns Nothing.
 */
function openNewConversation(): void {
  newConversationOpen.value = true
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

onMounted(async () => {
  projects.value = await listProjects().catch(() => [])
  await refresh()
  loading.value = false
  timer = setInterval(refresh, 8000)
})

onBeforeUnmount(() => {
  if (timer) clearInterval(timer)
})
</script>
