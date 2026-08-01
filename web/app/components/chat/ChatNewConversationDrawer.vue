<template>
  <AppDrawer
    :open="open"
    :title="isResume ? t('chat.new.resumeTitle') : t('chat.new.title')"
    :subtitle="isResume ? t('chat.new.resumeSubtitle') : t('chat.new.subtitle')"
    :icon="isResume ? 'i-lucide-history' : 'i-lucide-message-square-plus'"
    @close="emit('close')"
  >
    <div v-if="!projects.length && !isResume" class="flex flex-col items-center gap-3 py-8 text-center">
      <UIcon name="i-lucide-folder-plus" class="text-3xl text-[var(--app-ink-soft)]" />
      <p class="max-w-xs text-sm text-[var(--app-ink-soft)]">{{ t('chat.new.noProjects') }}</p>
      <UButton color="primary" icon="i-lucide-plus" @click="emit('create-project')">
        {{ t('chat.new.createProject') }}
      </UButton>
    </div>

    <div v-else class="flex flex-col gap-4">
      <!-- Resume banner -->
      <div
        v-if="isResume"
        class="flex items-start gap-2.5 rounded-lg border border-[var(--app-line)] bg-[var(--app-surface-2)] px-3 py-2.5"
      >
        <UIcon name="i-lucide-history" class="mt-0.5 h-4 w-4 shrink-0 text-[var(--app-accent)]" />
        <div class="min-w-0">
          <p class="truncate text-sm font-medium text-[var(--app-ink)]">{{ resumeLabel }}</p>
          <p v-if="preset?.cwd" class="mt-0.5 truncate font-mono text-xs text-[var(--app-ink-soft)]">
            {{ preset.cwd }}
          </p>
        </div>
      </div>

      <UFormField :label="t('chat.new.machine')">
        <AppNativeSelect
          :model-value="machineId ?? null"
          :items="machineOptions"
          :placeholder="t('chat.new.machinePlaceholder')"
          @update:model-value="machineId = toNumber($event)"
        />
      </UFormField>

      <UFormField
        :label="t('chat.new.project')"
        :help="isResume && !projectId ? t('chat.new.projectResumeHint') : undefined"
      >
        <div class="flex items-center gap-2">
          <AppNativeSelect
            :model-value="projectId ?? null"
            :items="projectOptions"
            :placeholder="t('chat.new.projectPlaceholder')"
            class="flex-1"
            @update:model-value="projectId = toNumber($event)"
          />
          <UButton
            color="neutral"
            variant="outline"
            icon="i-lucide-plus"
            :aria-label="t('chat.new.createProject')"
            @click="emit('create-project')"
          />
        </div>
      </UFormField>

      <PromptMetaPicker
        v-model:provider="provider"
        v-model:model="model"
        v-model:effort="effort"
        v-model:fast-mode="fast"
        native
      />

      <UFormField :label="t('chat.new.message')">
        <UTextarea
          v-model="text"
          :rows="4"
          autoresize
          :placeholder="isResume ? t('chat.new.messagePlaceholderResume') : t('chat.new.messagePlaceholder')"
          class="w-full"
        />
      </UFormField>
    </div>

    <template v-if="projects.length || isResume" #footer>
      <UButton color="neutral" variant="outline" class="flex-1" :disabled="submitting" @click="emit('close')">
        {{ t('common.close') }}
      </UButton>
      <UButton
        color="primary"
        :icon="isResume ? 'i-lucide-play' : 'i-lucide-send'"
        class="flex-1"
        :loading="submitting"
        :disabled="!canSubmit"
        @click="submit"
      >
        {{ isResume ? t('chat.new.resume') : t('chat.new.start') }}
      </UButton>
    </template>
  </AppDrawer>
</template>

<script lang="ts" setup>
import { computed, ref, watch } from 'vue'
import type { AiProvider } from '~/constants/modelPresets'
import type { Machine, NewConversationPreset, Project, Run } from '~/types'
import { createConversation } from '~/services/runsService'

/**
 * New / resume conversation drawer — native selects (machine first), provider/model,
 * then the opening message. Resuming is driven by a preset from the hub session list.
 */
const props = defineProps<{
  open: boolean
  projects: Project[]
  machines: Machine[]
  preset?: NewConversationPreset | null
}>()

const emit = defineEmits<{
  close: []
  created: [run: Run]
  'create-project': []
}>()

const { t } = useI18n()
const toast = useToast()

const CONTINUE_PROMPT = "Vas-y, continue là où tu t'étais arrêté."

const machineId = ref<number | undefined>(undefined)
const projectId = ref<number | undefined>(undefined)
const provider = ref<AiProvider | null>('claude')
const model = ref<string | null>('sonnet')
const effort = ref<string | null>('max')
const fast = ref(false)
const text = ref('')
const submitting = ref(false)

const isResume = computed(() => Boolean(props.preset?.sessionId))
const projectOptions = computed(() => props.projects.map((p) => ({ label: p.name, value: p.id })))
const machineOptions = computed(() =>
  props.machines.map((m) => ({
    label: `${m.name}${m.online ? '' : ` ${t('chat.new.offlineTag')}`}`,
    value: m.id,
  })),
)
const resumeLabel = computed(
  () => props.preset?.title || t('chat.new.resumeSessionShort', { id: props.preset?.sessionId?.slice(0, 8) ?? '' }),
)
const canSubmit = computed(() => Boolean(projectId.value && machineId.value && (text.value.trim() || isResume.value)))

/**
 * Coerce a native-select value to a machine/project id.
 * @param value - The raw select value.
 * @returns The numeric id or undefined.
 */
function toNumber(value: string | number | null): number | undefined {
  return typeof value === 'number' ? value : undefined
}

/**
 * Seed the form each time the drawer opens (fresh conversation or resume preset).
 * @returns Nothing.
 */
function initForm(): void {
  const preset = props.preset
  if (preset) {
    // Resume is always a Claude session — reset to a valid Claude model.
    machineId.value = preset.machineId
    projectId.value = preset.projectId ?? undefined
    provider.value = 'claude'
    model.value = 'sonnet'
    effort.value = 'max'
    fast.value = false
    text.value = ''
    return
  }
  const online = props.machines.find((m) => m.online)
  machineId.value = online?.id ?? props.machines[0]?.id
  projectId.value = props.projects[0]?.id
  provider.value = 'claude'
  model.value = 'sonnet'
  effort.value = 'max'
  fast.value = false
  text.value = ''
}

/**
 * Start the conversation (or resume a session) and hand the run back to the hub.
 * @returns Nothing.
 */
async function submit(): Promise<void> {
  if (!canSubmit.value || !projectId.value || !machineId.value || submitting.value) {
    return
  }
  const content = text.value.trim() || (isResume.value ? CONTINUE_PROMPT : '')
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
        claude_session_id: isResume.value ? props.preset?.sessionId : null,
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
      initForm()
    }
  },
)
</script>
