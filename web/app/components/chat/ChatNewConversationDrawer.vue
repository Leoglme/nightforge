<template>
  <AppDrawer
    :open="open"
    :title="t('chat.new.title')"
    :subtitle="t('chat.new.subtitle')"
    icon="i-lucide-message-square-plus"
    @close="emit('close')"
  >
    <div v-if="!projects.length" class="flex flex-col items-center gap-3 py-8 text-center">
      <UIcon name="i-lucide-folder-plus" class="text-3xl text-[var(--app-ink-soft)]" />
      <p class="max-w-xs text-sm text-[var(--app-ink-soft)]">{{ t('chat.new.noProjects') }}</p>
      <UButton color="primary" icon="i-lucide-plus" @click="emit('create-project')">
        {{ t('chat.new.createProject') }}
      </UButton>
    </div>

    <div v-else class="flex flex-col gap-4">
      <UFormField :label="t('chat.new.project')">
        <USelectMenu
          v-model="projectId"
          :items="projectOptions"
          value-key="value"
          label-key="label"
          :placeholder="t('chat.new.projectPlaceholder')"
          icon="i-lucide-folder-git-2"
          class="w-full"
          size="lg"
          :ui="{ content: 'z-[60]' }"
        >
          <template #content-bottom>
            <div class="border-t border-[var(--ui-border)] p-1">
              <button
                type="button"
                class="flex w-full items-center gap-2 rounded-md px-2 py-1.5 text-left text-sm text-[var(--app-ink-soft)] transition-colors hover:bg-[var(--ui-bg-elevated)] hover:text-[var(--app-ink)]"
                @click="emit('create-project')"
              >
                <UIcon name="i-lucide-folder-plus" class="h-4 w-4 shrink-0" />
                <span>{{ t('chat.new.createProject') }}</span>
              </button>
            </div>
          </template>
        </USelectMenu>
      </UFormField>

      <UFormField
        :label="t('chat.new.machine')"
        :help="selectedMachine && !machineOnline ? t('chat.new.machineOfflineHint') : undefined"
      >
        <USelectMenu
          v-model="machineId"
          :items="machineOptions"
          value-key="value"
          label-key="label"
          :placeholder="t('chat.new.machinePlaceholder')"
          icon="i-lucide-monitor"
          class="w-full"
          size="lg"
          :ui="{ content: 'z-[60]' }"
        />
      </UFormField>

      <PromptMetaPicker
        v-model:provider="provider"
        v-model:model="model"
        v-model:effort="effort"
        v-model:fast-mode="fast"
      />

      <ComposerSessionPicker
        v-if="canResumeProvider"
        v-model="sessionId"
        :machine-id="machineId"
        :local-path="localPath"
        :offline="!machineOnline"
      />

      <UFormField :label="t('chat.new.message')">
        <UTextarea
          v-model="text"
          :rows="4"
          autoresize
          :placeholder="sessionId ? t('chat.new.messagePlaceholderResume') : t('chat.new.messagePlaceholder')"
          class="w-full"
        />
      </UFormField>
    </div>

    <template v-if="projects.length" #footer>
      <UButton color="neutral" variant="outline" class="flex-1" :disabled="submitting" @click="emit('close')">
        {{ t('common.close') }}
      </UButton>
      <UButton
        color="primary"
        icon="i-lucide-send"
        class="flex-1"
        :loading="submitting"
        :disabled="!canSubmit"
        @click="submit"
      >
        {{ t('chat.new.start') }}
      </UButton>
    </template>
  </AppDrawer>
</template>

<script lang="ts" setup>
import { computed, ref, watch } from 'vue'
import type { AiProvider } from '~/constants/modelPresets'
import type { Machine, Project, Run } from '~/types'
import { listProjectPaths } from '~/services/projectsService'
import { createConversation } from '~/services/runsService'

/**
 * New remote conversation drawer — pick a project, machine, provider/model,
 * optionally resume a Claude session, then send the opening message.
 */
const props = defineProps<{
  open: boolean
  projects: Project[]
  machines: Machine[]
}>()

const emit = defineEmits<{
  close: []
  created: [run: Run]
  'create-project': []
}>()

const { t } = useI18n()
const toast = useToast()

const CONTINUE_PROMPT = "Vas-y, continue là où tu t'étais arrêté."

const projectId = ref<number | undefined>(undefined)
const machineId = ref<number | undefined>(undefined)
const provider = ref<AiProvider | null>('claude')
const model = ref<string | null>('sonnet')
const effort = ref<string | null>('max')
const fast = ref(false)
const sessionId = ref<string | null>(null)
const text = ref('')
const submitting = ref(false)
const pathByMachine = ref<Record<number, string>>({})

const projectOptions = computed(() => props.projects.map((p) => ({ label: p.name, value: p.id })))
const machineOptions = computed(() =>
  props.machines.map((m) => ({
    label: `${m.name}${m.online ? '' : ` ${t('chat.new.offlineTag')}`}`,
    value: m.id,
  })),
)

const selectedMachine = computed(() => props.machines.find((m) => m.id === machineId.value) ?? null)
const machineOnline = computed(() => Boolean(selectedMachine.value?.online))
const localPath = computed(() => (machineId.value ? (pathByMachine.value[machineId.value] ?? null) : null))

/** Session resume is Claude-only — the Cursor Agent CLI has no --resume. */
const canResumeProvider = computed(() => provider.value === 'claude')

const canSubmit = computed(() =>
  Boolean(projectId.value && machineId.value && (text.value.trim() || (sessionId.value && canResumeProvider.value))),
)

/**
 * Load the selected project's local clone paths (per machine) for session resume.
 * @param id - Project id.
 * @returns Nothing.
 */
async function loadPaths(id: number): Promise<void> {
  const paths = await listProjectPaths(id).catch(() => [])
  const map: Record<number, string> = {}
  for (const path of paths) {
    map[path.machine_id] = path.local_path
  }
  pathByMachine.value = map
}

/**
 * Seed defaults when the drawer opens (first online machine, first project).
 * @returns Nothing.
 */
function initDefaults(): void {
  if (!machineId.value) {
    const online = props.machines.find((m) => m.online)
    machineId.value = online?.id ?? props.machines[0]?.id
  }
  if (!projectId.value) {
    projectId.value = props.projects[0]?.id
  }
}

/**
 * Start the conversation: create a quick run seeded with the opening message.
 * @returns Nothing.
 */
async function submit(): Promise<void> {
  if (!canSubmit.value || !projectId.value || !machineId.value || submitting.value) {
    return
  }
  const content = text.value.trim() || (sessionId.value ? CONTINUE_PROMPT : '')
  if (!content) {
    return
  }
  submitting.value = true
  try {
    const run = await createConversation({
      machine_id: machineId.value,
      project_id: projectId.value,
      first_message: {
        content,
        provider: provider.value,
        claude_model: model.value,
        effort: effort.value,
        fast_mode: fast.value,
        claude_session_id: canResumeProvider.value ? sessionId.value : null,
      },
    })
    emit('created', run)
  } catch (err) {
    toast.add({
      title: t('chat.new.failed'),
      description: err instanceof Error ? err.message : undefined,
      color: 'error',
    })
  } finally {
    submitting.value = false
  }
}

watch(
  () => props.open,
  (open) => {
    if (open) {
      initDefaults()
      if (projectId.value) {
        loadPaths(projectId.value)
      }
    }
  },
)

watch(projectId, (id) => {
  sessionId.value = null
  if (id) {
    loadPaths(id)
  }
})

watch(provider, (value) => {
  if (value !== 'claude') {
    sessionId.value = null
  }
})
</script>
