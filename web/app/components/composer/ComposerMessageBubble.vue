<template>
  <div class="flex justify-end">
    <div
      class="w-full max-w-[92%] rounded-2xl rounded-br-md border border-[var(--app-line)] bg-[var(--app-accent-soft)] px-3 py-2 shadow-sm lg:px-4 lg:py-3"
    >
      <div class="mb-1.5 flex items-center justify-between gap-2 lg:mb-2">
        <div class="flex items-center gap-2">
          <span class="app-label">Message {{ index + 1 }}</span>
          <span
            v-if="message.source_item_ids?.length"
            class="rounded-full bg-[var(--app-surface)] px-2 py-0.5 text-[0.6rem] text-[var(--app-ink-soft)]"
          >
            {{ message.source_item_ids.length }} prompt(s)
          </span>
        </div>
        <div class="flex items-center gap-0.5">
          <UButton
            size="xs"
            color="neutral"
            variant="ghost"
            icon="i-lucide-arrow-up"
            :disabled="index === 0"
            @click="emit('move-up')"
          />
          <UButton
            size="xs"
            color="neutral"
            variant="ghost"
            icon="i-lucide-arrow-down"
            :disabled="index === total - 1"
            @click="emit('move-down')"
          />
          <UButton size="xs" color="neutral" variant="ghost" icon="i-lucide-pencil" @click="emit('edit')" />
          <UButton size="xs" color="error" variant="ghost" icon="i-lucide-trash-2" @click="emit('delete')" />
        </div>
      </div>

      <div v-if="editing" class="flex flex-col gap-2">
        <UTextarea :model-value="editText" :rows="4" autoresize @update:model-value="emit('update-edit', $event)" />
        <div class="flex gap-2">
          <UButton size="xs" color="primary" @click="emit('save')">Enregistrer</UButton>
          <UButton size="xs" color="neutral" variant="ghost" @click="emit('cancel-edit')">Annuler</UButton>
        </div>
      </div>
      <p v-else class="text-sm leading-relaxed whitespace-pre-wrap">{{ message.content }}</p>
    </div>
  </div>
</template>

<script lang="ts" setup>
import type { ProjectMessage } from '~/types'

/**
 * A single composed night message shown as a chat bubble (user side).
 */
defineProps<{
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
</script>
