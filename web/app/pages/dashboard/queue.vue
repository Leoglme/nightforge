<template>
  <div class="-mx-2 flex flex-col gap-5 sm:mx-0">
    <header class="flex flex-col gap-3 px-2 sm:px-0">
      <div class="flex items-start justify-between gap-3">
        <div>
          <h1 class="app-page-title">{{ t('nav.queue') }}</h1>
          <p class="text-xs text-[var(--app-ink-soft)] sm:text-sm">
            Carnet de prompts : note-les, copie-les, ou lance-les à la volée sans passer par le Composer.
          </p>
        </div>
        <div class="flex shrink-0 items-center gap-2">
          <UButton
            color="primary"
            variant="soft"
            icon="i-lucide-sparkles"
            class="shrink-0"
            :disabled="!projectId"
            @click="ideasOpen = true"
          >
            <span class="hidden sm:inline">Aide IA</span>
          </UButton>
          <UButton
            to="/dashboard/compose"
            color="neutral"
            variant="ghost"
            icon="i-lucide-messages-square"
            class="shrink-0"
          >
            <span class="hidden sm:inline">Composer</span>
          </UButton>
        </div>
      </div>

      <div class="flex flex-col gap-2 sm:flex-row sm:flex-wrap sm:items-center">
        <USelectMenu
          v-model="projectId"
          :items="projectOptions"
          value-key="value"
          label-key="label"
          placeholder="Choisir un projet"
          icon="i-lucide-folder-git-2"
          class="w-full sm:max-w-xs"
          size="lg"
        >
          <template #content-bottom>
            <div class="border-t border-[var(--ui-border)] p-1">
              <button
                type="button"
                class="flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left text-sm text-[var(--app-ink-soft)] transition-colors hover:bg-[var(--ui-bg-elevated)] hover:text-[var(--app-ink)]"
                @click="openCreateProject"
              >
                <UIcon name="i-lucide-folder-plus" class="h-4 w-4 shrink-0" />
                <span>Créer un projet s’il n’est pas dans la liste</span>
              </button>
            </div>
          </template>
        </USelectMenu>
        <USelectMenu
          v-if="machineOptions.length"
          v-model="machineId"
          :items="machineOptions"
          value-key="value"
          label-key="label"
          placeholder="Machine"
          icon="i-lucide-monitor"
          class="w-full sm:max-w-xs"
          size="lg"
        />
      </div>
    </header>

    <div
      v-if="!loading && projects.length === 0"
      class="app-card mx-2 flex flex-col items-center gap-3 px-6 py-12 text-center sm:mx-0"
    >
      <UIcon name="i-lucide-folder-plus" class="text-3xl text-[var(--app-ink-soft)]" />
      <p class="max-w-sm text-sm text-[var(--app-ink-soft)]">
        Aucun projet pour l’instant. Crée-en un ici pour commencer à noter des prompts.
      </p>
      <UButton color="primary" icon="i-lucide-plus" @click="openCreateProject">Créer un projet</UButton>
    </div>

    <template v-else-if="projectId">
      <div class="app-card mx-2 flex flex-col gap-3 p-3 sm:mx-0 sm:p-4">
        <UInput v-model="draftTitle" placeholder="Titre optionnel…" class="w-full" />
        <UTextarea
          v-model="draft"
          :rows="3"
          autoresize
          placeholder="Le prompt à envoyer… (Entrée pour ajouter, Maj+Entrée pour un saut de ligne)"
          class="w-full"
          @keydown.enter.exact.prevent="add"
        />
        <PromptMetaPicker
          v-model:provider="draftProvider"
          v-model:model="draftModel"
          v-model:effort="draftEffort"
          v-model:fast-mode="draftFast"
        />
        <div class="flex items-center justify-between gap-2">
          <span class="text-xs text-[var(--app-ink-soft)]">
            {{ pendingCount }} prompt(s) à faire
            <template v-if="doneCount"> · {{ doneCount }} terminé(s)</template>
          </span>
          <UButton color="primary" icon="i-lucide-plus" :disabled="!draft.trim()" :loading="adding" @click="add">
            Ajouter
          </UButton>
        </div>
      </div>

      <div class="flex flex-wrap items-center justify-between gap-2 px-3 sm:px-0">
        <label class="flex items-center gap-2 text-xs text-[var(--app-ink-soft)]">
          <USwitch v-model="showDone" size="sm" />
          Afficher les prompts terminés
        </label>
      </div>

      <div v-if="visibleItems.length" class="flex flex-wrap items-center justify-between gap-2 px-3 sm:px-0">
        <label class="flex items-center gap-2 text-xs text-[var(--app-ink-soft)]">
          <UCheckbox
            :model-value="allSelected"
            :indeterminate="someSelected && !allSelected"
            @update:model-value="toggleAll"
          />
          {{ selected.length ? `${selected.length} sélectionné(s)` : 'Tout sélectionner' }}
        </label>
        <div class="flex flex-wrap items-center gap-2">
          <UButton
            v-if="selected.length"
            color="primary"
            size="sm"
            icon="i-lucide-play"
            :loading="launching"
            :disabled="!machineId"
            @click="launchSelected"
          >
            Lancer ({{ selected.length }})
          </UButton>
          <UButton
            v-if="selected.length"
            color="error"
            variant="outline"
            size="sm"
            icon="i-lucide-trash-2"
            :loading="deleting"
            @click="deleteSelected"
          >
            Supprimer ({{ selected.length }})
          </UButton>
        </div>
      </div>

      <div v-if="loading" class="flex justify-center py-10">
        <UIcon name="i-lucide-loader-circle" class="animate-spin text-2xl text-[var(--app-ink-soft)]" />
      </div>
      <div
        v-else-if="visibleItems.length === 0"
        class="app-card mx-2 px-6 py-10 text-center text-sm text-[var(--app-ink-soft)] sm:mx-0"
      >
        <template v-if="showDone && items.length > 0">Aucun prompt en attente. Tous sont terminés.</template>
        <template v-else>File vide. Ajoute ta première idée ci-dessus.</template>
      </div>
      <ul v-else class="flex flex-col gap-2 px-2 sm:px-0">
        <li
          v-for="item in visibleItems"
          :key="item.id"
          :class="[
            'group flex items-start gap-3 rounded-lg border px-3 py-2.5 transition-colors',
            item.status === 'DONE'
              ? 'border-[var(--app-line)] bg-[var(--app-surface-2)] opacity-80'
              : selected.includes(item.id)
                ? 'border-[var(--app-accent)] bg-[var(--app-accent-soft)]'
                : 'border-[var(--app-line)] bg-[var(--app-surface)] hover:border-[var(--app-ink-soft)]',
          ]"
        >
          <UCheckbox
            v-if="item.status !== 'DONE'"
            :model-value="selected.includes(item.id)"
            class="mt-0.5"
            @click.stop
            @update:model-value="toggle(item.id)"
          />
          <UIcon v-else name="i-lucide-check-circle-2" class="mt-0.5 shrink-0 text-[var(--app-green)]" />
          <div class="min-w-0 flex-1">
            <div class="mb-1 flex flex-wrap items-center gap-1.5">
              <StatusBadge :status="item.status" />
              <span
                v-if="metaBadge(item)"
                class="rounded bg-[var(--app-surface-2)] px-1.5 py-0.5 text-[10px] font-medium text-[var(--app-ink-soft)]"
              >
                {{ metaBadge(item) }}
              </span>
            </div>
            <p v-if="item.title" class="mb-0.5 text-xs font-medium text-[var(--app-ink)]">{{ item.title }}</p>
            <span
              :class="[
                'text-sm leading-relaxed whitespace-pre-wrap',
                item.status === 'DONE' ? 'text-[var(--app-ink-soft)] line-through' : '',
              ]"
            >
              {{ item.prompt }}
            </span>
          </div>
          <div class="flex shrink-0 flex-row items-center gap-1">
            <UButton
              v-if="item.status !== 'DONE'"
              size="sm"
              color="primary"
              variant="soft"
              icon="i-lucide-play"
              title="Lancer maintenant"
              :loading="launchingId === item.id"
              :disabled="!machineId || launching"
              @click.stop="launchOne(item)"
            />
            <UButton
              size="sm"
              color="neutral"
              variant="ghost"
              icon="i-lucide-copy"
              title="Copier le prompt"
              @click.stop="copyItem(item)"
            />
            <UButton
              v-if="item.status !== 'DONE'"
              size="sm"
              color="error"
              variant="ghost"
              icon="i-lucide-trash-2"
              title="Supprimer"
              @click.stop="deleteOne(item.id)"
            />
          </div>
        </li>
      </ul>
    </template>

    <AppDrawer
      :open="ideasOpen"
      title="Aide prompts IA"
      subtitle="Idées en vrac → prompts prêts dans la file"
      icon="i-lucide-sparkles"
      @close="ideasOpen = false"
    >
      <div class="flex flex-col gap-4">
        <p class="text-sm text-[var(--app-ink-soft)]">
          Colle un pavé d’idées ou des mots-clés. NightForge découpe, rédige les prompts et choisit le modèle (Composer
          2.5 si dispo, sinon Claude Haiku). Machine en ligne = expansion IA ; sinon heuristique locale.
        </p>

        <UFormField label="Projet">
          <USelectMenu
            v-model="ideasProjectId"
            :items="projectOptions"
            value-key="value"
            label-key="label"
            placeholder="Projet"
            icon="i-lucide-folder-git-2"
            class="w-full"
            size="lg"
            :ui="{ content: 'z-[80]' }"
          >
            <template #content-bottom>
              <div class="border-t border-[var(--ui-border)] p-1">
                <button
                  type="button"
                  class="flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left text-sm text-[var(--app-ink-soft)] transition-colors hover:bg-[var(--ui-bg-elevated)] hover:text-[var(--app-ink)]"
                  @click="openCreateProject"
                >
                  <UIcon name="i-lucide-folder-plus" class="h-4 w-4 shrink-0" />
                  <span>Créer un projet s’il n’est pas dans la liste</span>
                </button>
              </div>
            </template>
          </USelectMenu>
        </UFormField>

        <UFormField label="Machine (expansion IA)">
          <USelectMenu
            v-if="machineOptions.length"
            v-model="ideasMachineId"
            :items="machineOptions"
            value-key="value"
            label-key="label"
            placeholder="Machine"
            icon="i-lucide-monitor"
            class="w-full"
            size="lg"
            :ui="{ content: 'z-[80]' }"
          />
        </UFormField>

        <UFormField label="Idées / mots-clés">
          <UTextarea
            v-model="ideasText"
            :rows="8"
            autoresize
            placeholder="- fix bouton pause&#10;- drawer plus fluide&#10;- SEO page légale…"
            class="w-full"
          />
        </UFormField>
      </div>

      <template #footer>
        <UButton color="neutral" variant="outline" class="flex-1" :disabled="expanding" @click="ideasOpen = false">
          Annuler
        </UButton>
        <UButton
          color="primary"
          class="flex-1"
          icon="i-lucide-wand-sparkles"
          :loading="expanding"
          :disabled="!ideasText.trim() || !ideasProjectId"
          @click="expandAndAdd"
        >
          Ajouter à la file
        </UButton>
      </template>
    </AppDrawer>

    <CreateProjectDrawer
      :open="createProjectOpen"
      :machine-id="machineId"
      :machine-name="selectedMachineName"
      @close="createProjectOpen = false"
      @created="onProjectCreated"
    />
  </div>
</template>

<script lang="ts" setup>
import { computed, onMounted, ref, watch } from 'vue'
import type { AiProvider } from '~/constants/modelPresets'
import { formatPromptMeta } from '~/constants/modelPresets'
import type { Machine, Project, QueueItem } from '~/types'
import { listMachines } from '~/services/machinesService'
import { listProjects } from '~/services/projectsService'
import { addQueueItem, deleteQueueItem, expandIdeas, listQueue } from '~/services/queueService'
import { createRun } from '~/services/runsService'

/**
 * Queue page — prompt notebook with on-the-fly launch (no Composer required).
 */
definePageMeta({ layout: 'dashboard', middleware: 'auth' })

const { t } = useI18n()
const toast = useToast()
const router = useRouter()

const projects = ref<Project[]>([])
const machines = ref<Machine[]>([])
const projectId = ref<number | undefined>(undefined)
const machineId = ref<number | undefined>(undefined)
const items = ref<QueueItem[]>([])
const selected = ref<number[]>([])
const draft = ref('')
const draftTitle = ref('')
const draftProvider = ref<AiProvider | null>('claude')
const draftModel = ref<string | null>('sonnet')
const draftEffort = ref<string | null>('max')
const draftFast = ref(false)
const loading = ref(true)
const adding = ref(false)
const deleting = ref(false)
const launching = ref(false)
const launchingId = ref<number | null>(null)
const showDone = ref(false)
const ideasOpen = ref(false)
const ideasText = ref('')
const ideasProjectId = ref<number | undefined>(undefined)
const ideasMachineId = ref<number | undefined>(undefined)
const expanding = ref(false)
const createProjectOpen = ref(false)

const projectOptions = computed(() => projects.value.map((p) => ({ label: p.name, value: p.id })))
const machineOptions = computed(() =>
  machines.value.map((m) => ({
    label: `${m.name}${m.online ? '' : ' (hors ligne)'}`,
    value: m.id,
  })),
)
const selectedMachineName = computed(() => machines.value.find((m) => m.id === machineId.value)?.name)
const visibleItems = computed(() =>
  showDone.value ? items.value : items.value.filter((item) => item.status !== 'DONE'),
)
const pendingCount = computed(() => items.value.filter((item) => item.status !== 'DONE').length)
const doneCount = computed(() => items.value.filter((item) => item.status === 'DONE').length)
const allSelected = computed(
  () =>
    visibleItems.value.filter((i) => i.status !== 'DONE').length > 0 &&
    selected.value.length === visibleItems.value.filter((i) => i.status !== 'DONE').length,
)
const someSelected = computed(() => selected.value.length > 0)

/**
 * Badge text for a queue item.
 */
function metaBadge(item: QueueItem): string {
  return formatPromptMeta({
    provider: item.provider as AiProvider | null,
    model: item.model,
    effort: item.effort,
    fastMode: item.fast_mode,
  })
}

/**
 * Open the quick create-project drawer.
 * @returns Nothing.
 */
function openCreateProject(): void {
  createProjectOpen.value = true
}

/**
 * After creating a project, select it and refresh the local list.
 * @param project - Newly created project.
 * @returns Nothing.
 */
async function onProjectCreated(project: Project): Promise<void> {
  const fresh = await listProjects().catch(() => null)
  if (fresh) {
    projects.value = fresh
  } else if (!projects.value.some((p) => p.id === project.id)) {
    projects.value = [...projects.value, project]
  }
  projectId.value = project.id
  ideasProjectId.value = project.id
  await loadQueue()
}

/**
 * Copy prompt (+ meta hint) to clipboard.
 */
async function copyItem(item: QueueItem): Promise<void> {
  const meta = metaBadge(item)
  const text = meta ? `${meta}\n${item.prompt}` : item.prompt
  try {
    await navigator.clipboard.writeText(text)
    toast.add({ title: 'Prompt copié', color: 'success' })
  } catch {
    toast.add({ title: 'Impossible de copier', color: 'error' })
  }
}

/**
 * Launch selected (or given) queue items on the chosen machine immediately.
 */
async function launchItems(ids: number[]): Promise<void> {
  if (!projectId.value || !machineId.value || ids.length === 0 || launching.value) {
    return
  }
  launching.value = true
  try {
    const run = await createRun({
      machine_id: machineId.value,
      project_ids: [projectId.value],
      quota_count: 1,
      parallel: false,
      wait_for_fresh_quota: false,
      queue_item_ids: ids,
    })
    selected.value = []
    toast.add({
      title: ids.length === 1 ? 'Prompt lancé' : `${ids.length} prompts lancés`,
      color: 'success',
    })
    await router.push(`/dashboard/runs/${run.id}`)
  } catch (err) {
    toast.add({
      title: 'Impossible de lancer',
      description: err instanceof Error ? err.message : undefined,
      color: 'error',
    })
  } finally {
    launching.value = false
    launchingId.value = null
  }
}

async function launchOne(item: QueueItem): Promise<void> {
  launchingId.value = item.id
  await launchItems([item.id])
}

async function launchSelected(): Promise<void> {
  await launchItems([...selected.value])
}

async function loadQueue(): Promise<void> {
  if (!projectId.value) {
    items.value = []
    return
  }
  loading.value = true
  selected.value = []
  try {
    items.value = await listQueue(projectId.value, true).catch(() => [])
  } finally {
    loading.value = false
  }
}

async function add(): Promise<void> {
  const text = draft.value.trim()
  if (!text || !projectId.value || adding.value) {
    return
  }
  adding.value = true
  try {
    const item = await addQueueItem(projectId.value, {
      prompt: text,
      title: draftTitle.value.trim() || null,
      provider: draftProvider.value,
      model: draftModel.value,
      effort: draftEffort.value,
      fast_mode: draftFast.value,
      created_from: 'web',
    })
    items.value = [...items.value, item]
    draft.value = ''
    draftTitle.value = ''
  } finally {
    adding.value = false
  }
}

/**
 * Expand ideas via agent/heuristic and append to the project queue.
 */
async function expandAndAdd(): Promise<void> {
  const text = ideasText.value.trim()
  if (!text || !ideasProjectId.value || expanding.value) {
    return
  }
  expanding.value = true
  try {
    const result = await expandIdeas(ideasProjectId.value, {
      ideas: text,
      machine_id: ideasMachineId.value ?? null,
      prefer_provider: 'cursor',
    })
    projectId.value = ideasProjectId.value
    await loadQueue()
    ideasText.value = ''
    ideasOpen.value = false
    const via =
      result.source === 'agent'
        ? `via ${result.provider_used || 'agent'} (${result.model_used || '?'})`
        : 'heuristique locale'
    toast.add({
      title: `${result.items.length} prompt(s) ajouté(s)`,
      description: result.summary ? `${result.summary} — ${via}` : via,
      color: 'success',
    })
  } catch (err) {
    toast.add({
      title: 'Expansion impossible',
      description: err instanceof Error ? err.message : undefined,
      color: 'error',
    })
  } finally {
    expanding.value = false
  }
}

function toggle(id: number): void {
  selected.value = selected.value.includes(id) ? selected.value.filter((x) => x !== id) : [...selected.value, id]
}

function toggleAll(): void {
  const pending = visibleItems.value.filter((i) => i.status !== 'DONE').map((i) => i.id)
  selected.value = allSelected.value ? [] : pending
}

async function deleteOne(id: number): Promise<void> {
  if (!projectId.value) {
    return
  }
  await deleteQueueItem(projectId.value, id)
  items.value = items.value.filter((i) => i.id !== id)
  selected.value = selected.value.filter((x) => x !== id)
}

async function deleteSelected(): Promise<void> {
  if (!projectId.value || selected.value.length === 0 || deleting.value) {
    return
  }
  deleting.value = true
  const ids = [...selected.value]
  try {
    await Promise.all(ids.map((id) => deleteQueueItem(projectId.value as number, id)))
    items.value = items.value.filter((i) => !ids.includes(i.id))
    selected.value = []
    toast.add({ title: `${ids.length} prompt(s) supprimé(s)`, color: 'success' })
  } finally {
    deleting.value = false
  }
}

watch(projectId, loadQueue)

watch(ideasOpen, (open) => {
  if (open) {
    ideasProjectId.value = projectId.value ?? projects.value[0]?.id
    ideasMachineId.value = machineId.value ?? machines.value.find((m) => m.online)?.id ?? machines.value[0]?.id
  }
})

watch(showDone, () => {
  selected.value = selected.value.filter((id) => visibleItems.value.some((item) => item.id === id))
})

onMounted(async () => {
  ;[projects.value, machines.value] = await Promise.all([
    listProjects().catch(() => []),
    listMachines().catch(() => []),
  ])
  projectId.value = projects.value[0]?.id
  const online = machines.value.find((m) => m.online)
  machineId.value = online?.id ?? machines.value[0]?.id
  loading.value = false
  if (projectId.value) {
    await loadQueue()
  }
})
</script>
