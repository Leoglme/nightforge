<template>
  <!-- Tighter horizontal padding on mobile (counteracts the layout's p-4) -->
  <div class="-mx-2 flex flex-col gap-5 sm:mx-0">
    <header class="flex flex-col gap-3 px-2 sm:px-0">
      <div class="flex items-start justify-between gap-3">
        <div>
          <h1 class="app-page-title">{{ t('nav.queue') }}</h1>
          <p class="text-xs text-[var(--app-ink-soft)] sm:text-sm">
            Note tes idées de prompts au fil de l'eau. Tu les réutilises ensuite dans le Composer.
          </p>
        </div>
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

      <USelectMenu
        v-if="projectOptions.length"
        v-model="projectId"
        :items="projectOptions"
        value-key="value"
        label-key="label"
        placeholder="Choisir un projet"
        icon="i-lucide-folder-git-2"
        class="w-full sm:max-w-xs"
        size="lg"
      />
    </header>

    <!-- No project yet -->
    <div
      v-if="!loading && projects.length === 0"
      class="app-card mx-2 flex flex-col items-center gap-3 px-6 py-12 text-center sm:mx-0"
    >
      <UIcon name="i-lucide-folder-plus" class="text-3xl text-[var(--app-ink-soft)]" />
      <p class="max-w-sm text-sm text-[var(--app-ink-soft)]">
        Aucun projet pour l'instant. Crée d'abord un projet depuis le Composer, puis reviens noter tes idées ici.
      </p>
      <UButton to="/dashboard/compose" color="primary" icon="i-lucide-plus">Aller au Composer</UButton>
    </div>

    <template v-else-if="projectId">
      <!-- Quick capture -->
      <div class="app-card mx-2 flex flex-col gap-2 p-3 sm:mx-0 sm:p-4">
        <UTextarea
          v-model="draft"
          :rows="2"
          autoresize
          placeholder="Une idée de prompt à réutiliser… (Entrée pour ajouter, Maj+Entrée pour un saut de ligne)"
          class="w-full"
          @keydown.enter.exact.prevent="add"
        />
        <div class="flex items-center justify-between gap-2">
          <span class="text-xs text-[var(--app-ink-soft)]">{{ items.length }} prompt(s) en file</span>
          <UButton color="primary" icon="i-lucide-plus" :disabled="!draft.trim()" :loading="adding" @click="add">
            Ajouter
          </UButton>
        </div>
      </div>

      <!-- Selection toolbar -->
      <div v-if="items.length" class="flex items-center justify-between gap-2 px-3 sm:px-0">
        <label class="flex items-center gap-2 text-xs text-[var(--app-ink-soft)]">
          <UCheckbox
            :model-value="allSelected"
            :indeterminate="someSelected && !allSelected"
            @update:model-value="toggleAll"
          />
          {{ selected.length ? `${selected.length} sélectionné(s)` : 'Tout sélectionner' }}
        </label>
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

      <!-- List -->
      <div v-if="loading" class="flex justify-center py-10">
        <UIcon name="i-lucide-loader-circle" class="animate-spin text-2xl text-[var(--app-ink-soft)]" />
      </div>
      <div
        v-else-if="items.length === 0"
        class="app-card mx-2 px-6 py-10 text-center text-sm text-[var(--app-ink-soft)] sm:mx-0"
      >
        File vide. Ajoute ta première idée ci-dessus.
      </div>
      <ul v-else class="flex flex-col gap-2 px-2 sm:px-0">
        <li
          v-for="item in items"
          :key="item.id"
          :class="[
            'group flex items-start gap-3 rounded-lg border px-3 py-2.5 transition-colors',
            selected.includes(item.id)
              ? 'border-[var(--app-accent)] bg-[var(--app-accent-soft)]'
              : 'border-[var(--app-line)] bg-[var(--app-surface)] hover:border-[var(--app-ink-soft)]',
          ]"
          @click="toggle(item.id)"
        >
          <UCheckbox
            :model-value="selected.includes(item.id)"
            class="mt-0.5"
            @click.stop
            @update:model-value="toggle(item.id)"
          />
          <span class="min-w-0 flex-1 text-sm leading-relaxed whitespace-pre-wrap">{{ item.prompt }}</span>
          <UButton
            size="xs"
            color="error"
            variant="ghost"
            icon="i-lucide-trash-2"
            class="shrink-0 opacity-60 transition-opacity group-hover:opacity-100"
            title="Supprimer"
            @click.stop="deleteOne(item.id)"
          />
        </li>
      </ul>
    </template>
  </div>
</template>

<script lang="ts" setup>
import { computed, onMounted, ref, watch } from 'vue'
import type { Project, QueueItem } from '~/types'
import { listProjects } from '~/services/projectsService'
import { addQueueItem, deleteQueueItem, listQueue } from '~/services/queueService'

/**
 * Queue page — a prominent, per-project backlog of reusable prompt ideas.
 * Quick capture on top, multi-select + bulk delete below. Prompts are picked into
 * night messages from the Composer's library panel.
 */
definePageMeta({ layout: 'dashboard', middleware: 'auth' })

const { t } = useI18n()
const toast = useToast()

const projects = ref<Project[]>([])
const projectId = ref<number | undefined>(undefined)
const items = ref<QueueItem[]>([])
const selected = ref<number[]>([])
const draft = ref('')
const loading = ref(true)
const adding = ref(false)
const deleting = ref(false)

const projectOptions = computed(() => projects.value.map((p) => ({ label: p.name, value: p.id })))
const allSelected = computed(() => items.value.length > 0 && selected.value.length === items.value.length)
const someSelected = computed(() => selected.value.length > 0)

/**
 * Load the queue for the current project.
 * @returns Nothing.
 */
async function loadQueue(): Promise<void> {
  if (!projectId.value) {
    items.value = []
    return
  }
  loading.value = true
  selected.value = []
  try {
    items.value = await listQueue(projectId.value).catch(() => [])
  } finally {
    loading.value = false
  }
}

/**
 * Add the drafted prompt to the current project's queue.
 * @returns Nothing.
 */
async function add(): Promise<void> {
  const text = draft.value.trim()
  if (!text || !projectId.value || adding.value) {
    return
  }
  adding.value = true
  try {
    const item = await addQueueItem(projectId.value, { prompt: text, created_from: 'web' })
    items.value = [...items.value, item]
    draft.value = ''
  } finally {
    adding.value = false
  }
}

/**
 * Toggle a single item in the selection.
 * @param id - Queue item id.
 * @returns Nothing.
 */
function toggle(id: number): void {
  selected.value = selected.value.includes(id) ? selected.value.filter((x) => x !== id) : [...selected.value, id]
}

/**
 * Select all items or clear the selection.
 * @returns Nothing.
 */
function toggleAll(): void {
  selected.value = allSelected.value ? [] : items.value.map((i) => i.id)
}

/**
 * Delete a single queue item.
 * @param id - Queue item id.
 * @returns Nothing.
 */
async function deleteOne(id: number): Promise<void> {
  if (!projectId.value) {
    return
  }
  await deleteQueueItem(projectId.value, id)
  items.value = items.value.filter((i) => i.id !== id)
  selected.value = selected.value.filter((x) => x !== id)
}

/**
 * Delete every selected queue item.
 * @returns Nothing.
 */
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

onMounted(async () => {
  projects.value = await listProjects().catch(() => [])
  projectId.value = projects.value[0]?.id
  loading.value = false
  if (projectId.value) {
    await loadQueue()
  }
})
</script>
