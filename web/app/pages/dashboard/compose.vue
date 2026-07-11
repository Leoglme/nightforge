<template>
  <div class="flex h-full flex-col">
    <!-- Unified launch toolbar: config lives in the Réglages drawer so the chat fills the page -->
    <div
      class="flex shrink-0 items-center gap-2 border-b border-[var(--app-line)] bg-[var(--app-surface)] px-3 py-2 lg:px-6 lg:py-3"
    >
      <UButton
        color="neutral"
        variant="outline"
        icon="i-lucide-sliders-horizontal"
        class="shrink-0"
        @click="showLaunchSettings = true"
      >
        Réglages
      </UButton>

      <div class="min-w-0 flex-1 truncate text-xs text-[var(--app-ink-soft)]">
        <span>{{ totalMessages }} msg · {{ selectedIds.length }} proj</span>
        <template v-if="selectedMachineName"> · {{ selectedMachineName }}</template>
        <template v-if="freshTimeLabel">
          · <span class="font-medium text-[var(--app-accent-ink)]">vierge {{ freshTimeLabel }}</span>
        </template>
      </div>

      <UButton
        color="primary"
        icon="i-lucide-moon-star"
        class="shrink-0"
        :disabled="selectedIds.length === 0 || !machineId || totalMessages === 0"
        :loading="launching"
        @click="launch"
      >
        <span class="hidden sm:inline">Lancer la nuit</span>
        <span class="sm:hidden">Lancer</span>
      </UButton>
    </div>

    <!-- 3-column body -->
    <div class="flex min-h-0 flex-1 flex-col lg:flex-row">
      <ComposerProjectList
        :projects="selectedProjects"
        :active-id="activeId"
        :message-count="countMessages"
        @select="activeId = $event"
        @add="openPicker"
      />

      <!-- Center: chat thread -->
      <section class="flex min-h-0 min-w-0 flex-1 flex-col bg-[var(--app-bg)]">
        <div v-if="!activeProject" class="flex flex-1 flex-col items-center justify-center gap-3 p-6 text-center">
          <UIcon name="i-lucide-messages-square" class="text-3xl text-[var(--app-ink-soft)]" />
          <p class="max-w-sm text-sm text-[var(--app-ink-soft)]">
            Ajoute un ou plusieurs projets à gauche, puis compose ici la séquence exacte des messages que Claude
            exécutera cette nuit.
          </p>
          <UButton color="primary" icon="i-lucide-plus" @click="openPicker">Ajouter un projet</UButton>
        </div>

        <template v-else>
          <div class="flex items-center justify-between gap-2 border-b border-[var(--app-line)] px-4 py-2">
            <div class="min-w-0">
              <div class="truncate text-sm font-medium">{{ activeProject.name }}</div>
              <div class="truncate text-xs text-[var(--app-ink-soft)]">{{ activeProject.github_repo }}</div>
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

          <div ref="threadEl" class="min-h-0 flex-1 space-y-4 overflow-y-auto px-4 py-4">
            <div
              v-if="activeMessages.length === 0"
              class="mx-auto max-w-md rounded-xl border border-dashed border-[var(--app-line)] py-10 text-center text-sm text-[var(--app-ink-soft)]"
            >
              <p class="mb-1 font-medium text-[var(--app-ink)]">Aucun message pour ce projet</p>
              <p>Écris ci-dessous ou pioche des prompts dans la bibliothèque.</p>
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

          <!-- Composer input (sticky bottom) -->
          <div class="shrink-0 border-t border-[var(--app-line)] bg-[var(--app-surface)] p-4">
            <div class="mb-3 grid gap-3 sm:grid-cols-2">
              <ComposerSessionPicker
                v-model="activeSessionId"
                :machine-id="machineId"
                :local-path="activeLocalPath"
                :offline="!selectedMachineOnline"
              />
              <ComposerModelPicker v-model="activeModelId" />
            </div>

            <UTextarea
              v-model="input"
              :rows="3"
              autoresize
              :placeholder="
                activeSessionId
                  ? 'Optionnel — laisse vide pour envoyer « Vas-y, continue » dans la session choisie'
                  : 'Écris le prochain message pour Claude Code…'
              "
              class="mb-2 w-full"
            />
            <div class="flex flex-wrap items-center justify-between gap-2">
              <span v-if="pickedIds.length" class="text-xs text-[var(--app-ink-soft)]">
                {{ pickedIds.length }} prompt(s) dans le brouillon
              </span>
              <span v-else-if="activeSessionId" class="text-xs text-[var(--app-accent-ink)]">
                Reprise de session activée
              </span>
              <span v-else class="text-xs text-[var(--app-ink-soft)]">Ajoute pour empiler le message</span>
              <div class="flex gap-2">
                <UButton
                  v-if="activeSessionId"
                  size="sm"
                  color="neutral"
                  variant="outline"
                  icon="i-lucide-play"
                  @click="addContinueMessage"
                >
                  Vas-y continue
                </UButton>
                <UButton size="sm" color="primary" icon="i-lucide-send" :disabled="!canAddMessage" @click="addMessage">
                  Ajouter
                </UButton>
              </div>
            </div>
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
    <AppDrawer
      :open="showCreateProject"
      title="Nouveau projet"
      subtitle="Dépôt Git que Claude fera avancer"
      icon="i-lucide-folder-plus"
      show-back
      @back="backToPicker"
      @close="showCreateProject = false"
    >
      <form id="create-project-form" class="flex flex-col gap-4" @submit.prevent="createNewProject">
        <UFormField label="Nom">
          <UInput v-model="createForm.name" class="w-full" size="lg" required placeholder="Mon projet" />
        </UFormField>
        <UFormField label="Dépôt GitHub" hint="owner/repo ou URL complète">
          <UInput v-model="createForm.github_repo" class="w-full" size="lg" required placeholder="dibodev/mon-projet" />
        </UFormField>
        <UFormField label="Branche de base">
          <UInput v-model="createForm.base_branch" class="w-full" size="lg" placeholder="main" />
        </UFormField>
      </form>

      <template #footer>
        <UButton color="neutral" variant="outline" class="flex-1" @click="backToPicker">Retour</UButton>
        <UButton
          type="submit"
          form="create-project-form"
          color="primary"
          class="flex-1"
          :loading="savingProject"
          :disabled="!createForm.name.trim() || !createForm.github_repo.trim()"
        >
          Créer
        </UButton>
      </template>
    </AppDrawer>

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
          <p class="app-label mb-1">Chemins locaux</p>
          <p class="mb-3 text-xs text-[var(--app-ink-soft)]">
            Où le dépôt est cloné sur chaque machine. L'agent y lance Claude Code, commit et push.
          </p>
          <div v-if="machines.length === 0" class="text-sm text-[var(--app-ink-soft)]">
            Ajoute d'abord une machine dans l'onglet Machines.
          </div>
          <div v-for="machine in machines" v-else :key="machine.id" class="mb-3">
            <UFormField :label="machine.name">
              <div class="flex gap-2">
                <UInput
                  v-model="pathInputs[machine.id]"
                  class="w-full flex-1"
                  placeholder="C:\\Users\\moi\\Projects\\mon-projet"
                />
                <UButton
                  color="neutral"
                  variant="outline"
                  icon="i-lucide-save"
                  :disabled="!pathInputs[machine.id]?.trim()"
                  @click="savePath(machine.id)"
                />
              </div>
            </UFormField>
          </div>
        </div>

        <div class="border-t border-[var(--app-line)] pt-4">
          <UButton color="error" variant="outline" icon="i-lucide-trash-2" block @click="removeProjectPermanently">
            Supprimer le projet
          </UButton>
        </div>
      </div>
    </AppDrawer>
  </div>
</template>

<script lang="ts" setup>
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import type { Machine, Project, ProjectMessage, QuotaPlan, QueueItem } from '~/types'
import { listMachines } from '~/services/machinesService'
import {
  createProject,
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

/**
 * Night composer — Claude-like 3-column UI to build per-project message sequences.
 * Project lifecycle (create / edit / paths / delete) and the prompt library are all
 * managed here through drawers, so no separate projects page is needed.
 */
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
const wakeAt = ref('')
const plan = ref<QuotaPlan | null>(null)
const planning = ref(false)
const launching = ref(false)
let planTimer: ReturnType<typeof setTimeout> | null = null

const showPicker = ref(false)
const showMobileLibrary = ref(false)
const showCreateProject = ref(false)
const showSettings = ref(false)
const showLaunchSettings = ref(false)

const createForm = reactive({ name: '', github_repo: '', base_branch: 'main' })
const savingProject = ref(false)

const settingsProject = ref<Project | null>(null)
const settingsForm = reactive({ name: '', github_repo: '', base_branch: 'main' })
const pathByProject = ref<Record<number, Record<number, string>>>({})
const sessionByProject = ref<Record<number, string | null>>({})
const modelByProject = ref<Record<number, string | null>>({})
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
  get: () => modelByProject.value[activeId.value] ?? null,
  set: (value: string | null) => {
    modelByProject.value[activeId.value] = value
  },
})
const canAddMessage = computed(() => Boolean(input.value.trim() || activeSessionId.value))
const freshTimeLabel = computed(() => (plan.value ? formatTimeFr(plan.value.fresh_quota_available_at) : ''))
const selectedProjects = computed(() =>
  selectedIds.value.map((id) => projects.value.find((p) => p.id === id)).filter((p): p is Project => Boolean(p)),
)
const activeProject = computed(() => projects.value.find((p) => p.id === activeId.value) ?? null)
const activeMessages = computed(() => messagesByProject.value[activeId.value] ?? [])
const activeQueue = computed(() => queueByProject.value[activeId.value] ?? [])
const totalMessages = computed(() =>
  selectedIds.value.reduce((sum, id) => sum + (messagesByProject.value[id]?.length ?? 0), 0),
)

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
  createForm.name = ''
  createForm.github_repo = ''
  createForm.base_branch = 'main'
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
 * Create a project, then select it and return to the picker.
 * @returns Nothing.
 */
async function createNewProject(): Promise<void> {
  if (!createForm.name.trim() || !createForm.github_repo.trim() || savingProject.value) {
    return
  }
  savingProject.value = true
  try {
    const project = await createProject({
      name: createForm.name.trim(),
      github_repo: createForm.github_repo.trim(),
      base_branch: createForm.base_branch.trim() || 'main',
    })
    await refreshProjects()
    const created = projects.value.find((p) => p.id === project.id) ?? project
    await toggleProject(created)
    showCreateProject.value = false
    toast.add({ title: 'Projet créé', color: 'success' })
  } finally {
    savingProject.value = false
  }
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
  pathInputs.value = {}
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
    })
    await refreshProjects()
    toast.add({ title: 'Projet mis à jour', color: 'success' })
  } finally {
    savingSettings.value = false
  }
}

/**
 * Save a project's local path on a machine.
 * @param machineId - The machine id.
 * @returns Nothing.
 */
async function savePath(machineId: number): Promise<void> {
  if (!settingsProject.value) {
    return
  }
  const localPath = pathInputs.value[machineId]?.trim()
  if (!localPath) {
    return
  }
  await setProjectPath(settingsProject.value.id, { machine_id: machineId, local_path: localPath })
  if (!pathByProject.value[settingsProject.value.id]) {
    pathByProject.value[settingsProject.value.id] = {}
  }
  pathByProject.value[settingsProject.value.id]![machineId] = localPath
  toast.add({ title: 'Chemin enregistré', color: 'success' })
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
  toast.add({ title: 'Projet supprimé', color: 'success' })
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
    claude_model: modelByProject.value[activeProject.value.id] ?? undefined,
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
    claude_model: modelByProject.value[activeProject.value.id] ?? undefined,
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
    claude_model: activeModelId.value ?? undefined,
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
watch([machineId, quotaCount, wakeAt], scheduleComputePlan)

onMounted(async () => {
  ;[projects.value, machines.value] = await Promise.all([
    listProjects().catch(() => []),
    listMachines().catch(() => []),
  ])

  // Anchor the timeline on the real reset straight away when there's only one machine.
  if (!machineId.value && machines.value.length === 1) {
    machineId.value = machines.value[0]!.id
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
