<template>
  <AppDrawer
    :open="open && !editing && !creating"
    title="Projets"
    subtitle="Gérer les dépôts liés à NightForge"
    icon="i-lucide-folder-git-2"
    @close="emit('close')"
  >
    <div v-if="loading" class="flex justify-center py-10">
      <UIcon name="i-lucide-loader-circle" class="animate-spin text-2xl text-[var(--app-ink-soft)]" />
    </div>

    <div v-else-if="projects.length === 0" class="flex flex-col items-center gap-3 py-10 text-center">
      <UIcon name="i-lucide-folder-plus" class="text-3xl text-[var(--app-ink-soft)]" />
      <p class="max-w-xs text-sm text-[var(--app-ink-soft)]">
        Aucun projet lié. Ajoute un dépôt Git pour pouvoir noter des prompts et lancer des runs.
      </p>
    </div>

    <ul v-else class="divide-y divide-[var(--app-line)]">
      <li v-for="project in projects" :key="project.id" class="flex items-start gap-3 py-3 first:pt-0 last:pb-0">
        <div class="min-w-0 flex-1">
          <div class="truncate text-sm font-medium text-[var(--app-ink)]">{{ project.name }}</div>
          <div class="truncate text-xs text-[var(--app-ink-soft)]">{{ project.github_repo }}</div>
          <div v-if="project.pending_count" class="mt-0.5 text-[11px] text-[var(--app-ink-soft)]">
            {{ project.pending_count }} prompt(s) en attente
          </div>
        </div>
        <div class="flex shrink-0 items-center gap-1">
          <UButton
            color="neutral"
            variant="ghost"
            size="sm"
            icon="i-lucide-settings-2"
            title="Modifier"
            aria-label="Modifier"
            @click="openEdit(project)"
          />
          <UButton
            color="error"
            variant="ghost"
            size="sm"
            icon="i-lucide-unlink"
            title="Détacher de NightForge"
            aria-label="Détacher de NightForge"
            :loading="detachingId === project.id"
            @click="detach(project)"
          />
        </div>
      </li>
    </ul>

    <template #footer>
      <UButton color="primary" icon="i-lucide-plus" class="flex-1" @click="creating = true">Nouveau projet</UButton>
    </template>
  </AppDrawer>

  <AppDrawer
    :open="open && editing"
    title="Modifier le projet"
    :subtitle="editProject?.name ?? undefined"
    icon="i-lucide-settings-2"
    show-back
    @back="closeEdit"
    @close="emit('close')"
  >
    <div v-if="editProject" class="flex flex-col gap-6">
      <form id="dashboard-edit-project-form" class="flex flex-col gap-4" @submit.prevent="saveEdit">
        <UFormField label="Nom">
          <UInput v-model="editForm.name" class="w-full" required />
        </UFormField>
        <UFormField label="Dépôt GitHub">
          <UInput v-model="editForm.github_repo" class="w-full" required />
        </UFormField>
        <UFormField label="Branche de base">
          <UInput v-model="editForm.base_branch" class="w-full" />
        </UFormField>
        <div class="flex flex-col gap-2">
          <UCheckbox v-model="editForm.allow_push" label="Autoriser le push automatique par l’IA" />
          <AppCallout variant="info">
            Désactivé = commits locaux uniquement. Tu pushes toi-même après review.
          </AppCallout>
        </div>
        <div class="flex flex-col gap-2">
          <UCheckbox
            v-model="editForm.push_to_main"
            label="Autoriser le push directement sur main"
            :disabled="!editForm.allow_push"
          />
          <AppCallout variant="info">
            Activé par défaut. Sinon NightForge crée une branche
            <code class="font-mono text-[0.7rem] text-[var(--app-ink)]">night/YYYY-MM-DD</code> à chaque run.
          </AppCallout>
        </div>
      </form>

      <div class="border-t border-[var(--app-line)] pt-4">
        <div v-if="machines.length === 0" class="text-sm text-[var(--app-ink-soft)]">Ajoute d’abord une machine.</div>
        <div v-for="machine in machines" v-else :key="machine.id" class="mb-3 last:mb-0">
          <ProjectLocalPathInput v-model="pathInputs[machine.id]" :machine-name="machine.name" />
        </div>
      </div>

      <div class="border-t border-[var(--app-line)] pt-4">
        <UButton
          color="error"
          variant="outline"
          icon="i-lucide-unlink"
          block
          :loading="detachingId === editProject.id"
          @click="detach(editProject)"
        >
          Détacher de NightForge
        </UButton>
      </div>
    </div>

    <template #footer>
      <UButton color="neutral" variant="outline" class="flex-1" @click="closeEdit">Retour</UButton>
      <UButton
        type="submit"
        form="dashboard-edit-project-form"
        color="primary"
        class="flex-1"
        :loading="saving"
        :disabled="!editForm.name.trim() || !editForm.github_repo.trim()"
      >
        Enregistrer
      </UButton>
    </template>
  </AppDrawer>

  <CreateProjectDrawer
    :open="open && creating"
    :machine-id="defaultMachineId"
    :machine-name="defaultMachineName"
    show-back
    @back="creating = false"
    @close="creating = false"
    @created="onCreated"
  />
</template>

<script lang="ts" setup>
import { computed, reactive, ref, watch } from 'vue'
import AppCallout from '~/components/AppCallout.vue'
import ProjectLocalPathInput from '~/components/ProjectLocalPathInput.vue'
import type { Machine, Project } from '~/types'
import { listMachines } from '~/services/machinesService'
import {
  deleteProject,
  listProjectPaths,
  listProjects,
  setProjectPath,
  updateProject,
} from '~/services/projectsService'

/**
 * Drawer to list, edit and detach projects from NightForge (not from disk).
 */
const props = defineProps<{
  open: boolean
}>()

const emit = defineEmits<{
  close: []
  changed: []
}>()

const toast = useToast()
const loading = ref(false)
const saving = ref(false)
const creating = ref(false)
const editing = ref(false)
const detachingId = ref<number | null>(null)
const projects = ref<Project[]>([])
const machines = ref<Machine[]>([])
const editProject = ref<Project | null>(null)
const pathInputs = ref<Record<number, string>>({})
const editForm = reactive({
  name: '',
  github_repo: '',
  base_branch: 'main',
  allow_push: true,
  push_to_main: true,
})

const defaultMachineId = computed(() => {
  const online = machines.value.find((m) => m.online)
  return online?.id ?? machines.value[0]?.id
})
const defaultMachineName = computed(() => machines.value.find((m) => m.id === defaultMachineId.value)?.name)

watch(
  () => props.open,
  async (open) => {
    if (!open) {
      creating.value = false
      editing.value = false
      editProject.value = null
      return
    }
    await reload()
  },
)

/**
 * Reload projects and machines.
 * @returns Nothing.
 */
async function reload(): Promise<void> {
  loading.value = true
  try {
    ;[projects.value, machines.value] = await Promise.all([
      listProjects().catch(() => []),
      listMachines().catch(() => []),
    ])
  } finally {
    loading.value = false
  }
}

/**
 * Open the edit panel for a project.
 * @param project - Project to edit.
 * @returns Nothing.
 */
async function openEdit(project: Project): Promise<void> {
  editProject.value = project
  editForm.name = project.name
  editForm.github_repo = project.github_repo
  editForm.base_branch = project.base_branch
  editForm.allow_push = project.allow_push !== false
  editForm.push_to_main = project.push_to_main !== false
  pathInputs.value = Object.fromEntries(machines.value.map((machine) => [machine.id, '']))
  editing.value = true
  const paths = await listProjectPaths(project.id).catch(() => [])
  for (const path of paths) {
    pathInputs.value[path.machine_id] = path.local_path
  }
}

/**
 * Close the edit panel and return to the list.
 * @returns Nothing.
 */
function closeEdit(): void {
  editing.value = false
  editProject.value = null
}

/**
 * Save edited project fields.
 * @returns Nothing.
 */
async function saveEdit(): Promise<void> {
  if (!editProject.value || saving.value) {
    return
  }
  saving.value = true
  try {
    await updateProject(editProject.value.id, {
      name: editForm.name.trim(),
      github_repo: editForm.github_repo.trim(),
      base_branch: editForm.base_branch.trim() || 'main',
      allow_push: editForm.allow_push,
      push_to_main: editForm.push_to_main,
    })
    const pathSaves = Object.entries(pathInputs.value)
      .filter(([, localPath]) => localPath?.trim())
      .map(([machineId, localPath]) =>
        setProjectPath(editProject.value!.id, {
          machine_id: Number(machineId),
          local_path: localPath.trim(),
        }),
      )
    await Promise.all(pathSaves)
    toast.add({ title: 'Projet mis à jour', color: 'success' })
    await reload()
    emit('changed')
    closeEdit()
  } catch {
    toast.add({ title: 'Impossible d’enregistrer', color: 'error' })
  } finally {
    saving.value = false
  }
}

/**
 * Detach a project from NightForge (API delete — disk untouched).
 * @param project - Project to detach.
 * @returns Nothing.
 */
async function detach(project: Project): Promise<void> {
  if (detachingId.value) {
    return
  }
  const ok = window.confirm(
    `Détacher « ${project.name} » de NightForge ?\n\nLe dossier sur ta machine et le dépôt GitHub ne sont pas touchés.`,
  )
  if (!ok) {
    return
  }
  detachingId.value = project.id
  try {
    await deleteProject(project.id)
    toast.add({ title: 'Projet détaché', color: 'success' })
    if (editProject.value?.id === project.id) {
      closeEdit()
    }
    await reload()
    emit('changed')
  } catch {
    toast.add({ title: 'Impossible de détacher', color: 'error' })
  } finally {
    detachingId.value = null
  }
}

/**
 * After creating a project, refresh the list.
 * @returns Nothing.
 */
async function onCreated(): Promise<void> {
  creating.value = false
  await reload()
  emit('changed')
}
</script>
