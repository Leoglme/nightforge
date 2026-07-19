<template>
  <div class="flex min-h-0 flex-1 flex-col">
    <!-- Unified launch toolbar: config lives in the Réglages drawer so the chat fills the page -->
    <div
      class="flex shrink-0 flex-col gap-2 border-b border-[var(--app-line)] bg-[var(--app-surface)] px-3 py-1.5 lg:flex-row lg:items-center lg:gap-3 lg:px-6 lg:py-3"
    >
      <div class="flex items-center gap-2">
        <UButton
          to="/dashboard"
          color="primary"
          icon="i-lucide-arrow-left"
          class="hidden shrink-0 md:inline-flex"
          size="sm"
        >
          {{ t('nav.back') }}
        </UButton>

        <UButton
          color="neutral"
          variant="outline"
          icon="i-lucide-sliders-horizontal"
          class="shrink-0"
          size="sm"
          @click="showLaunchSettings = true"
        >
          Réglages
        </UButton>

        <UButton
          color="primary"
          icon="i-lucide-moon-star"
          class="ml-auto shrink-0 lg:order-last lg:ml-0"
          size="sm"
          :disabled="selectedIds.length === 0 || !machineId || totalMessages === 0"
          :loading="launching"
          @click="launch"
        >
          Lancer la nuit
        </UButton>
      </div>

      <div
        class="hidden min-w-0 flex-col gap-0.5 text-xs text-[var(--app-ink-soft)] sm:flex sm:flex-row sm:flex-wrap sm:items-center sm:gap-x-2 lg:min-w-0 lg:flex-1 lg:justify-end"
      >
        <span>{{ launchSummary }}</span>
        <template v-if="selectedMachineName">
          <span class="hidden sm:inline">·</span>
          <span class="truncate font-medium text-[var(--app-ink)]">{{ selectedMachineName }}</span>
        </template>
        <template v-if="freshTimeLabel">
          <span class="hidden md:inline">·</span>
          <span class="hidden font-medium text-[var(--app-accent-ink)] md:inline"> vierge {{ freshTimeLabel }} </span>
        </template>
      </div>
    </div>

    <!-- 3-column body -->
    <div class="flex min-h-0 flex-1 flex-col lg:flex-row lg:items-stretch">
      <ComposerProjectList
        :projects="selectedProjects"
        :active-id="activeId"
        :message-count="countMessages"
        @select="activeId = $event"
        @add="openPicker"
      />

      <!-- Center: chat thread -->
      <section class="flex h-full min-h-0 min-w-0 flex-1 flex-col bg-[var(--app-bg)]">
        <div v-if="!activeProject" class="flex flex-1 flex-col items-center justify-center gap-3 p-6 text-center">
          <UIcon name="i-lucide-messages-square" class="text-3xl text-[var(--app-ink-soft)]" />
          <p class="max-w-sm text-sm text-[var(--app-ink-soft)]">
            Ajoute un ou plusieurs projets à gauche, puis compose ici la séquence exacte des messages que Claude
            exécutera cette nuit.
          </p>
          <UButton color="primary" icon="i-lucide-plus" @click="openPicker">Ajouter un projet</UButton>
        </div>

        <template v-else>
          <div
            class="flex items-center justify-between gap-2 border-b border-[var(--app-line)] px-3 py-1.5 lg:px-4 lg:py-2"
          >
            <div class="min-w-0 flex-1">
              <div class="truncate text-sm leading-tight font-medium">{{ activeProject.name }}</div>
              <div class="hidden truncate text-xs text-[var(--app-ink-soft)] sm:block">
                {{ activeProject.github_repo }}
              </div>
            </div>
            <div class="flex shrink-0 items-center gap-1">
              <UButton
                size="xs"
                color="neutral"
                variant="ghost"
                icon="i-lucide-library"
                class="lg:hidden"
                title="Bibliothèque de prompts"
                @click="showMobileLibrary = true"
              />
              <UButton
                size="xs"
                color="neutral"
                variant="ghost"
                icon="i-lucide-settings-2"
                title="Réglages du projet"
                @click="openSettings(activeProject)"
              />
              <UButton
                size="xs"
                color="neutral"
                variant="ghost"
                icon="i-lucide-x"
                title="Retirer de la nuit"
                @click="removeProject(activeProject.id)"
              />
            </div>
          </div>

          <div ref="threadEl" class="min-h-0 flex-1 space-y-5 overflow-y-auto px-3 py-3 sm:space-y-6 lg:px-4 lg:py-4">
            <div
              v-if="activeMessages.length === 0"
              class="mx-auto max-w-md py-12 text-center text-sm text-[var(--app-ink-soft)]"
            >
              <p class="mb-1 font-medium text-[var(--app-ink)]">{{ t('compose.emptyTitle') }}</p>
              <p>{{ t('compose.emptyHint') }}</p>
            </div>

            <ComposerMessageBubble
              v-for="(message, index) in activeMessages"
              :key="message.id"
              :message="message"
              :index="index"
              :total="activeMessages.length"
              :editing="editingId === message.id"
              :edit-text="editText"
              @move-up="move(index, -1)"
              @move-down="move(index, 1)"
              @edit="startEdit(message)"
              @delete="remove(message.id)"
              @save="saveEdit(message.id)"
              @cancel-edit="cancelEdit"
              @update-edit="editText = $event"
            />
          </div>

          <!-- Shared chat composer (same style as run page) -->
          <div class="shrink-0 border-t border-[var(--app-line)] bg-[var(--app-surface)] px-3 py-3 lg:px-4 lg:py-4">
            <ChatComposer
              full-width
              :text="input"
              :provider="activeProvider"
              :model="activeModelId"
              :effort="activeEffort"
              :fast-mode="activeFastMode"
              :can-send="canAddMessage"
              :placeholder="composerPlaceholder"
              :hint="composerHint"
              :show-continue="Boolean(activeSessionId)"
              :continue-label="t('compose.continue')"
              @update:text="input = $event"
              @update:provider="activeProvider = $event"
              @update:model="activeModelId = $event"
              @update:effort="activeEffort = $event"
              @update:fast-mode="activeFastMode = $event"
              @send="addMessage"
              @continue="addContinueMessage"
            >
              <template #controlsStart>
                <UPopover v-model:open="sessionPopoverOpen" :ui="{ content: 'p-3 w-[min(20rem,calc(100vw-1.5rem))]' }">
                  <button
                    type="button"
                    class="inline-flex min-h-9 cursor-pointer items-center gap-1.5 rounded-lg px-2 text-xs font-medium text-[var(--app-ink)] transition-colors hover:bg-[var(--app-surface-2)] sm:min-h-8"
                    :class="activeSessionId ? 'text-[var(--app-accent-ink)]' : ''"
                  >
                    <UIcon name="i-lucide-history" class="h-3.5 w-3.5 shrink-0" />
                    <span class="max-w-[7rem] truncate">{{ sessionPillLabel }}</span>
                  </button>
                  <template #content>
                    <ComposerSessionPicker
                      v-model="activeSessionId"
                      compact
                      :machine-id="machineId"
                      :local-path="activeLocalPath"
                      :offline="!selectedMachineOnline"
                    />
                  </template>
                </UPopover>
              </template>
            </ChatComposer>
          </div>
        </template>
      </section>

      <!-- Right: prompt library (desktop) -->
      <ComposerPromptPanel
        class="hidden lg:flex"
        :project-id="activeId"
        :project-name="activeProject?.name ?? null"
        :items="activeQueue"
        :picked-ids="pickedIds"
        @toggle-pick="togglePick"
        @clear-picks="pickedIds = []"
        @insert-draft="insertPickedToDraft"
        @create-message="createMessageFromPicks"
        @add-item="addQueuePrompt"
        @delete-item="deleteQueuePrompt"
      />
    </div>

    <!-- Mobile library drawer -->
    <AppDrawer
      :open="showMobileLibrary"
      title="Bibliothèque de prompts"
      :subtitle="activeProject?.name ?? undefined"
      icon="i-lucide-library"
      @close="showMobileLibrary = false"
    >
      <ComposerPromptPanel
        class="!w-full !border-0"
        :project-id="activeId"
        :project-name="activeProject?.name ?? null"
        :items="activeQueue"
        :picked-ids="pickedIds"
        @toggle-pick="togglePick"
        @clear-picks="pickedIds = []"
        @add-item="addQueuePrompt"
        @delete-item="deleteQueuePrompt"
        @insert-draft="
          () => {
            insertPickedToDraft()
            showMobileLibrary = false
          }
        "
        @create-message="
          () => {
            createMessageFromPicks()
            showMobileLibrary = false
          }
        "
      />
    </AppDrawer>

    <!-- Mobile launch settings drawer -->
    <AppDrawer
      :open="showLaunchSettings"
      title="Lancement de la nuit"
      subtitle="Machine, quotas et fenêtre"
      icon="i-lucide-sliders-horizontal"
      @close="showLaunchSettings = false"
    >
      <div class="flex flex-col gap-4">
        <UFormField label="Machine">
          <USelectMenu
            v-model="machineId"
            :items="machineOptions"
            value-key="value"
            label-key="label"
            placeholder="Choisir"
            class="w-full"
            size="lg"
            :ui="{ content: 'z-[60]' }"
          />
        </UFormField>
        <UFormField label="Quotas (5 h)">
          <UInput v-model.number="quotaCount" type="number" min="1" max="10" class="w-full" size="lg" />
        </UFormField>
        <UFormField
          label="Attendre le prochain quota vierge"
          help="Recommandé : la nuit démarre au reset Claude réel (~23h), pas tout de suite."
        >
          <USwitch v-model="waitForFreshQuota" />
        </UFormField>
        <UFormField label="Fin de fenêtre" help="Aujourd'hui, ou demain si l'heure est déjà passée.">
          <UInput v-model="wakeAt" type="time" class="w-full" size="lg" />
        </UFormField>
        <ComposerQuotaTimeline :plan="plan" :loading="planning" />
      </div>

      <template #footer>
        <UButton color="neutral" variant="outline" class="flex-1" @click="showLaunchSettings = false">Fermer</UButton>
        <UButton
          color="primary"
          icon="i-lucide-moon-star"
          class="flex-1"
          :disabled="selectedIds.length === 0 || !machineId || totalMessages === 0"
          :loading="launching"
          @click="launchFromDrawer"
        >
          Lancer
        </UButton>
      </template>
    </AppDrawer>

    <!-- Project picker drawer -->
    <AppDrawer
      :open="showPicker"
      title="Projets pour cette nuit"
      subtitle="Ajoute les projets à composer"
      icon="i-lucide-folder-git-2"
      @close="showPicker = false"
    >
      <div
        v-if="projects.length === 0"
        class="rounded-lg border border-dashed border-[var(--app-line)] p-4 text-center text-sm text-[var(--app-ink-soft)]"
      >
        Aucun projet pour l'instant. Crée ton premier projet ci-dessous.
      </div>
      <ul v-else class="flex flex-col gap-2">
        <li
          v-for="project in projects"
          :key="project.id"
          class="flex items-center justify-between gap-3 rounded-lg border border-[var(--app-line)] px-3 py-2"
        >
          <div class="min-w-0">
            <div class="truncate text-sm font-medium">{{ project.name }}</div>
            <div class="truncate text-xs text-[var(--app-ink-soft)]">{{ project.github_repo }}</div>
          </div>
          <UButton
            size="xs"
            :color="selectedIds.includes(project.id) ? 'error' : 'primary'"
            :variant="selectedIds.includes(project.id) ? 'outline' : 'solid'"
            @click="toggleProject(project)"
          >
            {{ selectedIds.includes(project.id) ? 'Retirer' : 'Ajouter' }}
          </UButton>
        </li>
      </ul>

      <template #footer>
        <UButton color="primary" icon="i-lucide-plus" class="flex-1" @click="openCreateProject">Nouveau projet</UButton>
      </template>
    </AppDrawer>

    <!-- Create project drawer -->
    <CreateProjectDrawer
      :open="showCreateProject"
      :machine-id="machineId"
      :machine-name="selectedMachineName"
      show-back
      @back="backToPicker"
      @close="showCreateProject = false"
      @created="onProjectCreatedFromDrawer"
    />

    <!-- Project settings drawer -->
    <AppDrawer
      :open="showSettings"
      title="Réglages du projet"
      :subtitle="settingsProject?.name ?? undefined"
      icon="i-lucide-settings-2"
      @close="showSettings = false"
    >
      <div v-if="settingsProject" class="flex flex-col gap-6">
        <form id="edit-project-form" class="flex flex-col gap-4" @submit.prevent="saveSettings">
          <UFormField label="Nom">
            <UInput v-model="settingsForm.name" class="w-full" required />
          </UFormField>
          <UFormField label="Dépôt GitHub">
            <UInput v-model="settingsForm.github_repo" class="w-full" required />
          </UFormField>
          <UFormField label="Branche de base">
            <UInput v-model="settingsForm.base_branch" class="w-full" />
          </UFormField>
          <div class="flex flex-col gap-2">
            <UCheckbox v-model="settingsForm.push_to_main" label="Autoriser le push directement sur main" />
            <AppCallout variant="info">
              Activé par défaut. Sinon NightForge crée une branche
              <code class="font-mono text-[0.7rem] text-[var(--app-ink)]">night/YYYY-MM-DD</code> à chaque run.
            </AppCallout>
          </div>
          <UButton
            type="submit"
            color="primary"
            block
            :loading="savingSettings"
            :disabled="!settingsForm.name.trim() || !settingsForm.github_repo.trim()"
          >
            Enregistrer
          </UButton>
        </form>

        <div class="border-t border-[var(--app-line)] pt-4">
          <div v-if="machines.length === 0" class="text-sm text-[var(--app-ink-soft)]">
            Ajoute d'abord une machine dans l'onglet Machines.
          </div>
          <div v-for="machine in machines" v-else :key="machine.id" class="mb-3 last:mb-0">
            <ProjectLocalPathInput v-model="pathInputs[machine.id]" :machine-name="machine.name" />
          </div>
        </div>

        <div class="border-t border-[var(--app-line)] pt-4">
          <UButton color="error" variant="outline" icon="i-lucide-unlink" block @click="removeProjectPermanently">
            Détacher de NightForge
          </UButton>
        </div>
      </div>
    </AppDrawer>
  </div>
</template>

<script lang="ts" setup>
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import AppCallout from '~/components/AppCallout.vue'
import type { Machine, Project, ProjectMessage, QuotaPlan, QueueItem } from '~/types'
import { listMachines } from '~/services/machinesService'
import {
  deleteProject,
  listProjectPaths,
  listProjects,
  setProjectPath,
  updateProject,
} from '~/services/projectsService'
import { addQueueItem, deleteQueueItem, listQueue } from '~/services/queueService'
import { createMessage, deleteMessage, listMessages, reorderMessages, updateMessage } from '~/services/messagesService'
import { planQuota } from '~/services/quotaService'
import { createRun } from '~/services/runsService'
import type { AiProvider } from '~/constants/modelPresets'

/**
 * Night composer — Claude-like 3-column UI to build per-project message sequences.
 * Project lifecycle (create / edit / paths / delete) and the prompt library are all
 * managed here through drawers, so no separate projects page is needed.
 */
const { t } = useI18n()
definePageMeta({ layout: 'dashboard', middleware: 'auth' })

const STORAGE_KEY = 'nf-compose-selected-ids'
const CONTINUE_PROMPT = "Vas-y, continue là où tu t'étais arrêté."

const router = useRouter()
const toast = useToast()

const projects = ref<Project[]>([])
const machines = ref<Machine[]>([])
const selectedIds = ref<number[]>([])
const activeId = ref(0)
const messagesByProject = ref<Record<number, ProjectMessage[]>>({})
const queueByProject = ref<Record<number, QueueItem[]>>({})

const input = ref('')
const editingId = ref<number | null>(null)
const editText = ref('')
const pickedIds = ref<number[]>([])
const threadEl = ref<HTMLElement | null>(null)

const machineId = ref<number | undefined>(undefined)
const quotaCount = ref(1)
const waitForFreshQuota = ref(true)
const wakeAt = ref('')
const plan = ref<QuotaPlan | null>(null)
const planning = ref(false)
const launching = ref(false)
let planTimer: ReturnType<typeof setTimeout> | null = null

const showPicker = ref(false)
const showMobileLibrary = ref(false)
const sessionPopoverOpen = ref(false)
const showCreateProject = ref(false)
const showSettings = ref(false)
const showLaunchSettings = ref(false)

const settingsProject = ref<Project | null>(null)
const settingsForm = reactive({ name: '', github_repo: '', base_branch: 'main', push_to_main: true })
const pathByProject = ref<Record<number, Record<number, string>>>({})
const sessionByProject = ref<Record<number, string | null>>({})
const modelByProject = ref<Record<number, string | null>>({})
const providerByProject = ref<Record<number, AiProvider | null>>({})
const effortByProject = ref<Record<number, string | null>>({})
const fastByProject = ref<Record<number, boolean>>({})
const pathInputs = ref<Record<number, string>>({})
const savingSettings = ref(false)

const machineOptions = computed(() => machines.value.map((m) => ({ label: m.name, value: m.id })))
const selectedMachineName = computed(() => machines.value.find((m) => m.id === machineId.value)?.name ?? '')
const selectedMachineOnline = computed(() => machines.value.find((m) => m.id === machineId.value)?.online ?? false)
const activeLocalPath = computed(() => {
  if (!activeId.value || !machineId.value) {
    return null
  }
  return pathByProject.value[activeId.value]?.[machineId.value] ?? null
})
const activeSessionId = computed({
  get: () => sessionByProject.value[activeId.value] ?? null,
  set: (value: string | null) => {
    sessionByProject.value[activeId.value] = value
  },
})
const activeModelId = computed({
  get: () => modelByProject.value[activeId.value] ?? 'sonnet',
  set: (value: string | null) => {
    modelByProject.value[activeId.value] = value
  },
})
const activeProvider = computed({
  get: () => providerByProject.value[activeId.value] ?? 'claude',
  set: (value: AiProvider | null) => {
    providerByProject.value[activeId.value] = value
  },
})
const activeEffort = computed({
  get: () => effortByProject.value[activeId.value] ?? 'max',
  set: (value: string | null) => {
    effortByProject.value[activeId.value] = value
  },
})
const activeFastMode = computed({
  get: () => fastByProject.value[activeId.value] ?? false,
  set: (value: boolean) => {
    fastByProject.value[activeId.value] = value
  },
})
const canAddMessage = computed(() => Boolean(input.value.trim() || activeSessionId.value))
const freshTimeLabel = computed(() => (plan.value ? formatTimeFr(plan.value.fresh_quota_available_at) : ''))
const selectedProjects = computed(() =>
  selectedIds.value.map((id) => projects.value.find((p) => p.id === id)).filter((p): p is Project => Boolean(p)),
)
const activeProject = computed(() => projects.value.find((p) => p.id === activeId.value) ?? null)
const activeMessages = computed(() => messagesByProject.value[activeId.value] ?? [])
const activeQueue = computed(() =>
  (queueByProject.value[activeId.value] ?? []).filter((item) => item.status !== 'DONE'),
)
const totalMessages = computed(() =>
  selectedIds.value.reduce((sum, id) => sum + (messagesByProject.value[id]?.length ?? 0), 0),
)

const launchSummary = computed(() => {
  const messages = totalMessages.value
  const projects = selectedIds.value.length
  const messageLabel = messages <= 1 ? 'message' : 'messages'
  const projectLabel = projects <= 1 ? 'projet' : 'projets'
  return `${messages} ${messageLabel} · ${projects} ${projectLabel}`
})

const composerPlaceholder = computed(() =>
  activeSessionId.value ? t('compose.placeholderContinue') : t('compose.placeholder'),
)

const composerHint = computed(() => {
  if (pickedIds.value.length) {
    return t('compose.hintPicks', { n: pickedIds.value.length })
  }
  if (activeSessionId.value) {
    return t('compose.hintSession')
  }
  return t('compose.hintAdd')
})

const sessionPillLabel = computed(() =>
  activeSessionId.value
    ? t('compose.sessionShort', { id: activeSessionId.value.slice(0, 8) })
    : t('compose.sessionNew'),
)

/**
 * Active provider/model metadata payload for createMessage.
 */
function activeMetaPayload(): {
  provider?: string
  claude_model?: string
  effort?: string
  fast_mode?: boolean
} {
  const pid = activeProject.value?.id ?? activeId.value
  return {
    provider: providerByProject.value[pid] ?? activeProvider.value ?? undefined,
    claude_model: modelByProject.value[pid] ?? activeModelId.value ?? undefined,
    effort: effortByProject.value[pid] ?? activeEffort.value ?? undefined,
    fast_mode: fastByProject.value[pid] ?? activeFastMode.value,
  }
}

/**
 * Prefer metadata from the first picked queue item when composing from the library.
 */
function metaFromPicks(): {
  provider?: string
  claude_model?: string
  effort?: string
  fast_mode?: boolean
} {
  const first = activeQueue.value.find((item) => pickedIds.value.includes(item.id))
  if (first?.provider || first?.model) {
    return {
      provider: first.provider ?? undefined,
      claude_model: first.model ?? undefined,
      effort: first.effort ?? undefined,
      fast_mode: first.fast_mode ?? false,
    }
  }
  return activeMetaPayload()
}

/**
 * Count messages for a project (sidebar badge).
 * @param projectId - Project id.
 * @returns Message count.
 */
function countMessages(projectId: number): number {
  return messagesByProject.value[projectId]?.length ?? 0
}

/**
 * Persist selected project ids to localStorage.
 * @returns Nothing.
 */
function persistSelection(): void {
  if (import.meta.client) {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(selectedIds.value))
  }
}

/**
 * Restore selected project ids from localStorage.
 * @returns The stored ids.
 */
function restoreSelection(): number[] {
  if (!import.meta.client) {
    return []
  }
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    return raw ? (JSON.parse(raw) as number[]) : []
  } catch {
    return []
  }
}

/**
 * Load messages and queue for a project.
 * @param projectId - Project id.
 * @returns Nothing.
 */
async function loadProjectData(projectId: number): Promise<void> {
  const [messages, queue, paths] = await Promise.all([
    listMessages(projectId).catch(() => []),
    listQueue(projectId).catch(() => []),
    listProjectPaths(projectId).catch(() => []),
  ])
  messagesByProject.value[projectId] = messages
  queueByProject.value[projectId] = queue
  const map: Record<number, string> = {}
  for (const path of paths) {
    map[path.machine_id] = path.local_path
  }
  pathByProject.value[projectId] = map
}

/**
 * Refresh the projects list from the server.
 * @returns Nothing.
 */
async function refreshProjects(): Promise<void> {
  projects.value = await listProjects().catch(() => [])
}

/**
 * Scroll the message thread to the bottom.
 * @returns Nothing.
 */
async function scrollThread(): Promise<void> {
  await nextTick()
  if (threadEl.value) {
    threadEl.value.scrollTop = threadEl.value.scrollHeight
  }
}

/**
 * Open the project picker drawer.
 * @returns Nothing.
 */
function openPicker(): void {
  showPicker.value = true
}

/**
 * Toggle a project in/out of the composer.
 * @param project - The project.
 * @returns Nothing.
 */
async function toggleProject(project: Project): Promise<void> {
  if (selectedIds.value.includes(project.id)) {
    removeProject(project.id)
    return
  }
  selectedIds.value.push(project.id)
  activeId.value = project.id
  await loadProjectData(project.id)
  persistSelection()
}

/**
 * Remove a project from the composer (drafts stay saved server-side).
 * @param projectId - The project id.
 * @returns Nothing.
 */
function removeProject(projectId: number): void {
  selectedIds.value = selectedIds.value.filter((id) => id !== projectId)
  if (activeId.value === projectId) {
    activeId.value = selectedIds.value[0] ?? 0
  }
  persistSelection()
}

/**
 * Open the create-project drawer (from the picker).
 * @returns Nothing.
 */
function openCreateProject(): void {
  showPicker.value = false
  showCreateProject.value = true
}

/**
 * Go back from the create-project drawer to the picker.
 * @returns Nothing.
 */
function backToPicker(): void {
  showCreateProject.value = false
  showPicker.value = true
}

/**
 * After creating a project from the drawer, select it and refresh paths.
 * @param project - Newly created project.
 * @returns Nothing.
 */
async function onProjectCreatedFromDrawer(project: Project): Promise<void> {
  await refreshProjects()
  const created = projects.value.find((p) => p.id === project.id) ?? project
  await toggleProject(created)
  if (machineId.value) {
    const paths = await listProjectPaths(created.id).catch(() => [])
    const map: Record<number, string> = {}
    for (const path of paths) {
      map[path.machine_id] = path.local_path
    }
    pathByProject.value[created.id] = map
  }
  showCreateProject.value = false
  showPicker.value = true
}

/**
 * Open the settings drawer for a project (edit fields + load paths).
 * @param project - The project.
 * @returns Nothing.
 */
async function openSettings(project: Project): Promise<void> {
  settingsProject.value = project
  settingsForm.name = project.name
  settingsForm.github_repo = project.github_repo
  settingsForm.base_branch = project.base_branch
  settingsForm.push_to_main = project.push_to_main !== false
  pathInputs.value = Object.fromEntries(machines.value.map((machine) => [machine.id, '']))
  showSettings.value = true
  const paths = await listProjectPaths(project.id).catch(() => [])
  for (const path of paths) {
    pathInputs.value[path.machine_id] = path.local_path
  }
}

/**
 * Save the edited project fields.
 * @returns Nothing.
 */
async function saveSettings(): Promise<void> {
  if (!settingsProject.value || savingSettings.value) {
    return
  }
  savingSettings.value = true
  try {
    await updateProject(settingsProject.value.id, {
      name: settingsForm.name.trim(),
      github_repo: settingsForm.github_repo.trim(),
      base_branch: settingsForm.base_branch.trim() || 'main',
      push_to_main: settingsForm.push_to_main,
    })
    const pathSaves = Object.entries(pathInputs.value)
      .filter(([, localPath]) => localPath?.trim())
      .map(([machineId, localPath]) =>
        setProjectPath(settingsProject.value!.id, {
          machine_id: Number(machineId),
          local_path: localPath.trim(),
        }),
      )
    await Promise.all(pathSaves)
    for (const [machineId, localPath] of Object.entries(pathInputs.value)) {
      if (!localPath?.trim()) {
        continue
      }
      if (!pathByProject.value[settingsProject.value.id]) {
        pathByProject.value[settingsProject.value.id] = {}
      }
      pathByProject.value[settingsProject.value.id]![Number(machineId)] = localPath.trim()
    }
    await refreshProjects()
    toast.add({ title: 'Projet mis à jour', color: 'success' })
  } finally {
    savingSettings.value = false
  }
}

/**
 * Permanently delete the settings project.
 * @returns Nothing.
 */
async function removeProjectPermanently(): Promise<void> {
  if (!settingsProject.value) {
    return
  }
  const id = settingsProject.value.id
  await deleteProject(id)
  removeProject(id)
  await refreshProjects()
  showSettings.value = false
  toast.add({ title: 'Projet détaché', color: 'success' })
}

/**
 * Add a reusable prompt to the active project's library.
 * @param prompt - The prompt text.
 * @returns Nothing.
 */
async function addQueuePrompt(prompt: string): Promise<void> {
  if (!activeProject.value) {
    return
  }
  const item = await addQueueItem(activeProject.value.id, { prompt, created_from: 'web' })
  queueByProject.value[activeProject.value.id] = [...(queueByProject.value[activeProject.value.id] ?? []), item]
}

/**
 * Delete a prompt from the active project's library.
 * @param itemId - The queue item id.
 * @returns Nothing.
 */
async function deleteQueuePrompt(itemId: number): Promise<void> {
  if (!activeProject.value) {
    return
  }
  await deleteQueueItem(activeProject.value.id, itemId)
  const list = queueByProject.value[activeProject.value.id] ?? []
  queueByProject.value[activeProject.value.id] = list.filter((item) => item.id !== itemId)
  pickedIds.value = pickedIds.value.filter((id) => id !== itemId)
}

/**
 * Build text from currently picked queue items.
 * @returns Combined prompt text.
 */
function pickedText(): string {
  return activeQueue.value
    .filter((item) => pickedIds.value.includes(item.id))
    .map((item) => item.prompt)
    .join('\n\n')
}

/**
 * Append picked prompts to the composer draft textarea.
 * @returns Nothing.
 */
function insertPickedToDraft(): void {
  const text = pickedText()
  if (!text) {
    return
  }
  input.value = input.value.trim() ? `${input.value.trim()}\n\n${text}` : text
}

/**
 * Create a message directly from picked library prompts.
 * @returns Nothing.
 */
async function createMessageFromPicks(): Promise<void> {
  if (!activeProject.value) {
    return
  }
  const text = pickedText()
  if (!text) {
    return
  }
  const message = await createMessage(activeProject.value.id, {
    content: text,
    source_item_ids: [...pickedIds.value],
    created_from: 'web',
    claude_session_id: sessionByProject.value[activeProject.value.id] ?? undefined,
    ...metaFromPicks(),
  })
  messagesByProject.value[activeProject.value.id] = [
    ...(messagesByProject.value[activeProject.value.id] ?? []),
    message,
  ]
  pickedIds.value = []
  await scrollThread()
}

/**
 * Append the composer input as a new message draft.
 * @returns Nothing.
 */
async function addMessage(): Promise<void> {
  if (!activeProject.value || !canAddMessage.value) {
    return
  }
  const sessionId = sessionByProject.value[activeProject.value.id] ?? undefined
  const content = input.value.trim() || (sessionId ? CONTINUE_PROMPT : '')
  if (!content) {
    return
  }
  const message = await createMessage(activeProject.value.id, {
    content,
    claude_session_id: sessionId,
    ...activeMetaPayload(),
    source_item_ids: pickedIds.value.length ? [...pickedIds.value] : undefined,
    created_from: 'web',
  })
  messagesByProject.value[activeProject.value.id] = [
    ...(messagesByProject.value[activeProject.value.id] ?? []),
    message,
  ]
  input.value = ''
  pickedIds.value = []
  await scrollThread()
}

/**
 * Add a continue message into the selected Claude session.
 * @returns Nothing.
 */
async function addContinueMessage(): Promise<void> {
  if (!activeProject.value || !activeSessionId.value) {
    return
  }
  const message = await createMessage(activeProject.value.id, {
    content: CONTINUE_PROMPT,
    claude_session_id: activeSessionId.value,
    ...activeMetaPayload(),
    created_from: 'web',
  })
  messagesByProject.value[activeProject.value.id] = [
    ...(messagesByProject.value[activeProject.value.id] ?? []),
    message,
  ]
  await scrollThread()
  toast.add({ title: 'Message « Vas-y continue » ajouté', color: 'success' })
}

/**
 * Start inline editing of a message.
 * @param message - The message to edit.
 * @returns Nothing.
 */
function startEdit(message: ProjectMessage): void {
  editingId.value = message.id
  editText.value = message.content
}

/**
 * Cancel inline editing.
 * @returns Nothing.
 */
function cancelEdit(): void {
  editingId.value = null
  editText.value = ''
}

/**
 * Save an edited message.
 * @param messageId - The message id.
 * @returns Nothing.
 */
async function saveEdit(messageId: number): Promise<void> {
  if (!activeProject.value || !editText.value.trim()) {
    return
  }
  const updated = await updateMessage(activeProject.value.id, messageId, {
    content: editText.value.trim(),
  })
  const list = messagesByProject.value[activeProject.value.id] ?? []
  messagesByProject.value[activeProject.value.id] = list.map((m) => (m.id === messageId ? updated : m))
  cancelEdit()
}

/**
 * Delete a message draft.
 * @param messageId - The message id.
 * @returns Nothing.
 */
async function remove(messageId: number): Promise<void> {
  if (!activeProject.value) {
    return
  }
  await deleteMessage(activeProject.value.id, messageId)
  const list = messagesByProject.value[activeProject.value.id] ?? []
  messagesByProject.value[activeProject.value.id] = list.filter((m) => m.id !== messageId)
}

/**
 * Move a message up or down and persist the new order.
 * @param index - Current index.
 * @param delta - -1 to move up, 1 to move down.
 * @returns Nothing.
 */
async function move(index: number, delta: number): Promise<void> {
  if (!activeProject.value) {
    return
  }
  const list = [...(messagesByProject.value[activeProject.value.id] ?? [])]
  const target = index + delta
  if (target < 0 || target >= list.length) {
    return
  }
  const [moved] = list.splice(index, 1)
  if (!moved) {
    return
  }
  list.splice(target, 0, moved)
  messagesByProject.value[activeProject.value.id] = list
  await reorderMessages(
    activeProject.value.id,
    list.map((m) => m.id),
  )
}

/**
 * Toggle a queue prompt in the library selection.
 * @param itemId - The queue item id.
 * @returns Nothing.
 */
function togglePick(itemId: number): void {
  pickedIds.value = pickedIds.value.includes(itemId)
    ? pickedIds.value.filter((id) => id !== itemId)
    : [...pickedIds.value, itemId]
}

/**
 * Resolve the "window end" time (HH:MM) to a full ISO datetime.
 *
 * Only a time is entered; the date is inferred as today, or tomorrow when that time has
 * already passed (e.g. it's 23:00 and you set 08:00). A night is never planned days ahead.
 * @returns The ISO string, or null when no time is set or it is invalid.
 */
function resolveWakeIso(): string | null {
  if (!wakeAt.value) {
    return null
  }
  const [h, m] = wakeAt.value.split(':').map(Number)
  if (Number.isNaN(h) || Number.isNaN(m)) {
    return null
  }
  const target = new Date()
  target.setHours(h, m, 0, 0)
  if (target.getTime() <= Date.now()) {
    target.setDate(target.getDate() + 1)
  }
  return target.toISOString()
}

/**
 * Compute the quota timeline estimate for the current machine, quota count and wake time.
 * @returns Nothing.
 */
async function computePlan(): Promise<void> {
  if (!quotaCount.value || quotaCount.value < 1) {
    plan.value = null
    return
  }
  planning.value = true
  try {
    plan.value = await planQuota({
      quota_count: quotaCount.value,
      wake_at: resolveWakeIso(),
      machine_id: machineId.value ?? null,
      wait_for_fresh_quota: waitForFreshQuota.value,
    })
  } catch {
    plan.value = null
  } finally {
    planning.value = false
  }
}

/**
 * Debounced auto-recompute of the quota timeline whenever inputs change.
 * @returns Nothing.
 */
function scheduleComputePlan(): void {
  if (planTimer) {
    clearTimeout(planTimer)
  }
  planTimer = setTimeout(computePlan, 350)
}

/**
 * Launch the night run with the composed sequences.
 * @returns Nothing.
 */
async function launch(): Promise<void> {
  if (!machineId.value || selectedIds.value.length === 0 || totalMessages.value === 0) {
    return
  }
  launching.value = true
  try {
    const run = await createRun({
      machine_id: machineId.value,
      project_ids: [...selectedIds.value],
      quota_count: quotaCount.value,
      parallel: selectedIds.value.length > 1,
      window_end: resolveWakeIso(),
      wait_for_fresh_quota: waitForFreshQuota.value,
    })
    toast.add({ title: 'Nuit lancée', color: 'success' })
    router.push(`/dashboard/runs/${run.id}`)
  } finally {
    launching.value = false
  }
}

/**
 * Launch from the mobile settings drawer, closing it first.
 * @returns Nothing.
 */
async function launchFromDrawer(): Promise<void> {
  showLaunchSettings.value = false
  await launch()
}

watch(activeId, async (id) => {
  if (id && !messagesByProject.value[id]) {
    await loadProjectData(id)
  }
})

// Keep the quota timeline live: recompute whenever the machine, quota count or wake time change.
watch([machineId, quotaCount, wakeAt, waitForFreshQuota], scheduleComputePlan)

onMounted(async () => {
  ;[projects.value, machines.value] = await Promise.all([
    listProjects().catch(() => []),
    listMachines().catch(() => []),
  ])

  // Anchor the timeline on the real reset straight away when there's only one machine.
  if (!machineId.value) {
    const online = machines.value.find((m) => m.online)
    if (online) {
      machineId.value = online.id
    } else if (machines.value.length === 1) {
      machineId.value = machines.value[0]!.id
    }
  }

  const restored = restoreSelection().filter((id) => projects.value.some((p) => p.id === id))
  if (restored.length) {
    selectedIds.value = restored
    activeId.value = restored[0]!
    await Promise.all(restored.map((id) => loadProjectData(id)))
  }

  await computePlan()
})

onBeforeUnmount(() => {
  if (planTimer) {
    clearTimeout(planTimer)
  }
})
</script>
