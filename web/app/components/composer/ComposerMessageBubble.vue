<template>
  <div class="flex justify-end">
    <div
      class="w-full max-w-[min(42rem,100%)] rounded-2xl rounded-br-md border border-[var(--app-line)] bg-[var(--app-surface-2)] px-3 py-2.5 sm:max-w-[min(42rem,94%)] sm:px-3.5"
    >
      <div class="mb-1.5 flex items-start justify-between gap-2 sm:items-center sm:gap-3">
        <div class="flex min-w-0 flex-wrap items-center gap-2">
          <span class="shrink-0 text-xs font-medium text-[var(--app-ink-soft)]">
            {{ t('compose.messageN', { n: index + 1 }) }}
          </span>
          <span
            v-if="message.source_item_ids?.length"
            class="rounded-md bg-[var(--app-surface)] px-1.5 py-0.5 text-[0.65rem] text-[var(--app-ink-soft)]"
          >
            {{ message.source_item_ids.length }} prompt(s)
          </span>
        </div>

        <div class="flex shrink-0 items-center gap-x-1.5 gap-y-0.5">
          <span
            v-if="modelOnlyLabel"
            class="mr-1 hidden max-w-[12rem] min-w-0 items-center gap-1 text-xs text-[var(--app-ink-soft)] sm:inline-flex"
          >
            <CursorLogo v-if="provider === 'cursor'" class="!h-3.5 !w-3.5 shrink-0" />
            <ClaudeLogo v-else class="!h-3.5 !w-3.5 shrink-0" />
            <span class="truncate">{{ modelOnlyLabel }}</span>
            <span v-if="effortLabel" class="shrink-0 opacity-70">· {{ effortLabel }}</span>
            <span v-if="message.fast_mode" class="shrink-0 text-[var(--app-accent-ink)]">· Fast</span>
          </span>
          <UButton
            size="xs"
            color="neutral"
            variant="ghost"
            icon="i-lucide-arrow-up"
            class="min-h-8 min-w-8 sm:min-h-0 sm:min-w-0"
            :disabled="index === 0"
            @click="emit('move-up')"
          />
          <UButton
            size="xs"
            color="neutral"
            variant="ghost"
            icon="i-lucide-arrow-down"
            class="min-h-8 min-w-8 sm:min-h-0 sm:min-w-0"
            :disabled="index === total - 1"
            @click="emit('move-down')"
          />
          <UButton
            size="xs"
            color="neutral"
            variant="ghost"
            icon="i-lucide-pencil"
            class="min-h-8 min-w-8 sm:min-h-0 sm:min-w-0"
            @click="emit('edit')"
          />
          <UButton
            size="xs"
            color="error"
            variant="ghost"
            icon="i-lucide-trash-2"
            class="min-h-8 min-w-8 sm:min-h-0 sm:min-w-0"
            @click="emit('delete')"
          />
        </div>
      </div>

      <!-- Mobile model line -->
      <div v-if="modelOnlyLabel" class="mb-1.5 flex items-center gap-1.5 text-xs text-[var(--app-ink-soft)] sm:hidden">
        <CursorLogo v-if="provider === 'cursor'" class="!h-3.5 !w-3.5 shrink-0" />
        <ClaudeLogo v-else class="!h-3.5 !w-3.5 shrink-0" />
        <span class="truncate">{{ modelOnlyLabel }}</span>
        <span v-if="effortLabel" class="shrink-0 opacity-70">· {{ effortLabel }}</span>
        <span v-if="message.fast_mode" class="shrink-0 text-[var(--app-accent-ink)]">· Fast</span>
      </div>

      <div v-if="editing" class="flex flex-col gap-2">
        <UTextarea :model-value="editText" :rows="4" autoresize @update:model-value="emit('update-edit', $event)" />
        <div class="flex gap-2">
          <UButton size="xs" color="primary" @click="emit('save')">{{ t('compose.save') }}</UButton>
          <UButton size="xs" color="neutral" variant="ghost" @click="emit('cancel-edit')">
            {{ t('compose.cancel') }}
          </UButton>
        </div>
      </div>
      <p v-else class="text-sm leading-relaxed break-words whitespace-pre-wrap text-[var(--app-ink)]">
        {{ message.content }}
      </p>
    </div>
  </div>
</template>

<script lang="ts" setup>
import { computed } from 'vue'
import type { AiProvider, EffortLevel } from '~/constants/modelPresets'
import { EFFORT_LABELS, modelLabel } from '~/constants/modelPresets'
import type { ProjectMessage } from '~/types'

/**
 * Composed night message as a user-side gray chat bubble (same style as run chat).
 */
const props = defineProps<{
  message: ProjectMessage
  index: number
  total: number
  editing: boolean
  editText: string
}>()

const emit = defineEmits<{
  'move-up': []
  'move-down': []
  edit: []
  delete: []
  save: []
  'cancel-edit': []
  'update-edit': [value: string]
}>()

const { t } = useI18n()

const provider = computed(() => (props.message.provider as AiProvider | null) ?? null)

const modelOnlyLabel = computed(() => modelLabel(provider.value, props.message.claude_model))

const effortLabel = computed(() => {
  const effort = props.message.effort
  if (!effort) {
    return null
  }
  const key = `runs.chat.effortLevels.${effort}`
  const translated = t(key)
  return translated !== key ? translated : (EFFORT_LABELS[effort as EffortLevel] ?? effort)
})
</script>
