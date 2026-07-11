<template>
  <aside
    class="flex w-full shrink-0 flex-col border-t border-[var(--app-line)] bg-[var(--app-surface)] lg:w-72 lg:border-t-0 lg:border-l"
  >
    <div class="flex items-center justify-between border-b border-[var(--app-line)] px-3 py-2">
      <div class="min-w-0">
        <span class="app-label">Bibliothèque</span>
        <p v-if="projectName" class="truncate text-xs text-[var(--app-ink-soft)]">{{ projectName }}</p>
      </div>
      <UButton v-if="pickedIds.length" size="xs" color="neutral" variant="ghost" @click="emit('clear-picks')">
        Effacer
      </UButton>
    </div>

    <p class="px-3 py-2 text-xs text-[var(--app-ink-soft)]">
      Prompts réutilisables du projet. Sélectionne-en un ou plusieurs pour composer un message.
    </p>

    <!-- Add a reusable prompt to the library -->
    <div v-if="projectId" class="flex gap-2 px-3 pb-2">
      <UInput
        v-model="newPrompt"
        class="w-full flex-1"
        size="sm"
        placeholder="Nouveau prompt réutilisable…"
        @keyup.enter="addPrompt"
      />
      <UButton
        size="sm"
        color="neutral"
        variant="outline"
        icon="i-lucide-plus"
        :disabled="!newPrompt.trim()"
        @click="addPrompt"
      />
    </div>

    <div class="min-h-0 flex-1 overflow-y-auto px-2 pb-2">
      <div v-if="!projectId" class="px-1 py-6 text-center text-xs text-[var(--app-ink-soft)]">
        Sélectionne un projet.
      </div>
      <div v-else-if="items.length === 0" class="px-1 py-6 text-center text-xs text-[var(--app-ink-soft)]">
        File vide. Ajoute un prompt réutilisable ci-dessus.
      </div>
      <ul v-else class="flex flex-col gap-1.5">
        <li
          v-for="item in items"
          :key="item.id"
          :class="[
            'group cursor-pointer rounded-lg border px-2.5 py-2 transition-colors',
            item.status === 'DONE'
              ? 'cursor-default border-[var(--app-line)] bg-[var(--app-surface-2)] opacity-70'
              : pickedIds.includes(item.id)
                ? 'border-[var(--app-accent)] bg-[var(--app-accent-soft)]'
                : 'border-[var(--app-line)] hover:border-[var(--app-ink-soft)]',
          ]"
          @click="item.status === 'DONE' ? undefined : emit('toggle-pick', item.id)"
        >
          <div class="flex items-start gap-2">
            <UCheckbox
              v-if="item.status !== 'DONE'"
              :model-value="pickedIds.includes(item.id)"
              class="mt-0.5"
              @click.stop
              @update:model-value="emit('toggle-pick', item.id)"
            />
            <UIcon v-else name="i-lucide-check-circle-2" class="mt-0.5 shrink-0 text-[var(--app-green)]" />
            <div class="min-w-0 flex-1">
              <StatusBadge v-if="item.status !== 'PENDING'" :status="item.status" class="mb-1" />
              <span
                :class="[
                  'text-xs leading-relaxed',
                  item.status === 'DONE' ? 'text-[var(--app-ink-soft)] line-through' : '',
                ]"
              >
                {{ item.prompt }}
              </span>
            </div>
            <UButton
              size="xs"
              color="error"
              variant="ghost"
              icon="i-lucide-trash-2"
              class="shrink-0 opacity-0 transition-opacity group-hover:opacity-100"
              @click.stop="emit('delete-item', item.id)"
            />
          </div>
        </li>
      </ul>
    </div>

    <div class="flex flex-col gap-2 border-t border-[var(--app-line)] p-3">
      <UButton
        size="sm"
        color="neutral"
        variant="outline"
        icon="i-lucide-text-cursor-input"
        :disabled="pickedIds.length === 0"
        @click="emit('insert-draft')"
      >
        Insérer dans le brouillon
      </UButton>
      <UButton
        size="sm"
        color="primary"
        icon="i-lucide-message-square-plus"
        :disabled="pickedIds.length === 0"
        @click="emit('create-message')"
      >
        Créer le message ({{ pickedIds.length }})
      </UButton>
    </div>
  </aside>
</template>

<script lang="ts" setup>
import { ref } from 'vue'
import type { QueueItem } from '~/types'

/**
 * Right panel — the project's prompt library (reusable queue items) for message assembly.
 */
defineProps<{
  projectId: number
  projectName: string | null
  items: QueueItem[]
  pickedIds: number[]
}>()

const emit = defineEmits<{
  'toggle-pick': [itemId: number]
  'clear-picks': []
  'insert-draft': []
  'create-message': []
  'add-item': [prompt: string]
  'delete-item': [itemId: number]
}>()

const newPrompt = ref('')

/**
 * Emit an add-item event for the typed prompt, then reset the input.
 * @returns Nothing.
 */
function addPrompt(): void {
  const text = newPrompt.value.trim()
  if (!text) {
    return
  }
  emit('add-item', text)
  newPrompt.value = ''
}
</script>
