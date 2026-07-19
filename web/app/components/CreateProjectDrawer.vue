<template>
  <AppDrawer
    :open="open"
    title="Nouveau projet"
    subtitle="Chemin du dépôt Git sur ta machine"
    icon="i-lucide-folder-plus"
    :show-back="showBack"
    @back="emit('back')"
    @close="emit('close')"
  >
    <form id="create-project-drawer-form" class="flex flex-col gap-4" @submit.prevent="submit">
      <ProjectLocalPathInput
        v-model="form.local_path"
        :machine-name="machineName"
        required
        autofocus
        :disabled="!machineId"
        @blur="probePath"
      />

      <p
        v-if="!machineId"
        class="rounded-lg border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-xs text-amber-200"
      >
        Choisis d’abord une machine (en ligne de préférence) pour lier le chemin.
      </p>

      <div
        v-if="preview.name || preview.github_repo || probing || probeError"
        class="rounded-lg border border-[var(--app-line)] bg-[var(--app-surface-2)] px-3 py-2.5 text-sm"
      >
        <p v-if="probing" class="text-[var(--app-ink-soft)]">Détection du dépôt…</p>
        <p v-else-if="probeError" class="text-amber-500">{{ probeError }}</p>
        <ul v-else class="space-y-1 text-[var(--app-ink-soft)]">
          <li>
            Nom :
            <span class="font-medium text-[var(--app-ink)]">{{ preview.name || '—' }}</span>
          </li>
          <li>
            Repo :
            <span class="font-medium text-[var(--app-ink)]">{{ preview.github_repo || 'à renseigner plus tard' }}</span>
          </li>
          <li v-if="preview.base_branch">
            Branche :
            <span class="font-medium text-[var(--app-ink)]">{{ preview.base_branch }}</span>
          </li>
        </ul>
      </div>

      <div class="flex flex-col gap-2">
        <div class="flex items-center justify-between gap-3">
          <label class="text-sm font-medium text-[var(--app-ink)]" for="push-to-main-switch">
            Push directement sur main
          </label>
          <USwitch id="push-to-main-switch" v-model="form.push_to_main" />
        </div>
        <AppCallout variant="info">
          Activé par défaut. Sinon NightForge crée une branche
          <code class="font-mono text-[0.7rem] text-[var(--app-ink)]">night/YYYY-MM-DD</code> à chaque run.
        </AppCallout>
      </div>
    </form>

    <template #footer>
      <UButton
        color="neutral"
        variant="outline"
        class="flex-1"
        :disabled="saving"
        @click="showBack ? emit('back') : emit('close')"
      >
        {{ showBack ? 'Retour' : 'Annuler' }}
      </UButton>
      <UButton
        type="submit"
        form="create-project-drawer-form"
        color="primary"
        class="flex-1"
        :loading="saving || probing"
        :disabled="!canSubmit"
      >
        Créer
      </UButton>
    </template>
  </AppDrawer>
</template>

<script lang="ts" setup>
import { computed, reactive, ref, watch } from 'vue'
import AppCallout from '~/components/AppCallout.vue'
import ProjectLocalPathInput from '~/components/ProjectLocalPathInput.vue'
import type { Project } from '~/types'
import { inspectRepo } from '~/services/machinesService'
import { createProject, setProjectPath } from '~/services/projectsService'

/**
 * Drawer: create a project from a local git path on a machine.
 */
const props = withDefaults(
  defineProps<{
    open: boolean
    machineId?: number
    machineName?: string
    showBack?: boolean
  }>(),
  {
    machineId: undefined,
    machineName: undefined,
    showBack: false,
  },
)

const emit = defineEmits<{
  close: []
  back: []
  created: [project: Project]
}>()

const toast = useToast()
const saving = ref(false)
const probing = ref(false)
const probeError = ref('')
const probeBlocked = ref(false)
const form = reactive({
  local_path: '',
  push_to_main: true,
})
const preview = reactive({
  name: '',
  github_repo: '',
  base_branch: 'main',
})

const canSubmit = computed(() =>
  Boolean(
    props.machineId &&
    form.local_path.trim() &&
    (preview.name || folderNameFromPath(form.local_path)) &&
    !probing.value &&
    !saving.value &&
    !probeBlocked.value,
  ),
)

watch(
  () => form.local_path,
  () => {
    probeBlocked.value = false
    if (!probing.value) {
      probeError.value = ''
    }
  },
)

watch(
  () => props.open,
  (open) => {
    if (open) {
      form.local_path = ''
      form.push_to_main = true
      preview.name = ''
      preview.github_repo = ''
      preview.base_branch = 'main'
      probeError.value = ''
      probeBlocked.value = false
    }
  },
)

/**
 * Last path segment as project name fallback.
 * @param path - Local filesystem path.
 * @returns Folder name.
 */
function folderNameFromPath(path: string): string {
  const cleaned = path.replace(/[/\\]+$/, '').trim()
  const parts = cleaned.split(/[/\\]/).filter(Boolean)
  return parts[parts.length - 1] || 'projet'
}

/**
 * Ask the agent to detect name / GitHub remote from the path.
 * @returns Nothing.
 */
async function probePath(): Promise<void> {
  const path = form.local_path.trim()
  if (!path) {
    return
  }
  preview.name = folderNameFromPath(path)
  if (!props.machineId) {
    probeError.value = 'Choisis une machine pour détecter le remote GitHub.'
    return
  }
  probing.value = true
  probeError.value = ''
  probeBlocked.value = false
  try {
    const result = await inspectRepo(props.machineId, path)
    if (result.name) {
      preview.name = result.name
    }
    if (result.github_repo) {
      preview.github_repo = result.github_repo
    }
    if (result.base_branch) {
      preview.base_branch = result.base_branch
    }
    if (!result.exists) {
      probeError.value = 'Ce chemin n’existe pas sur la machine.'
      probeBlocked.value = true
    } else if (!result.is_git) {
      probeError.value = result.error || 'Ce dossier n’est pas un dépôt Git.'
      probeBlocked.value = true
    }
  } catch {
    probeError.value =
      'Machine hors ligne ou agent indisponible — le nom du dossier sera utilisé, le repo pourra être complété plus tard.'
  } finally {
    probing.value = false
  }
}

/**
 * Create the project + machine path, then notify the parent.
 * @returns Nothing.
 */
async function submit(): Promise<void> {
  const path = form.local_path.trim()
  if (!canSubmit.value || !props.machineId || !path || saving.value) {
    return
  }
  if (!preview.name) {
    await probePath()
  }
  const name = (preview.name || folderNameFromPath(path)).trim()
  if (!name) {
    return
  }
  saving.value = true
  try {
    const project = await createProject({
      name,
      github_repo: preview.github_repo.trim() || undefined,
      base_branch: preview.base_branch.trim() || 'main',
      push_to_main: form.push_to_main,
    })
    await setProjectPath(project.id, {
      machine_id: props.machineId,
      local_path: path,
    })
    toast.add({ title: 'Projet créé', color: 'success' })
    emit('created', project)
    emit('close')
  } catch {
    toast.add({ title: 'Impossible de créer le projet', color: 'error' })
  } finally {
    saving.value = false
  }
}
</script>
