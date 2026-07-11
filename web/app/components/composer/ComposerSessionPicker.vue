<template>
  <div :class="compact ? '' : 'rounded-lg border border-[var(--app-line)] bg-[var(--app-surface-2)] p-3'">
    <div :class="['flex items-center justify-between gap-2', compact ? 'mb-1.5' : 'mb-2']">
      <span class="app-label flex items-center gap-1.5">
        <UIcon name="i-lucide-history" class="text-[var(--app-accent)]" />
        Session Claude existante
      </span>
      <UIcon v-if="loading" name="i-lucide-loader-circle" class="animate-spin text-[var(--app-ink-soft)]" />
    </div>

    <p v-if="!machineId || !localPath" class="text-xs text-[var(--app-ink-soft)]">
      Choisis une machine et configure le chemin local du projet pour lister les sessions (desktop ou CLI).
    </p>

    <p v-else-if="offline" class="text-xs text-[var(--app-ink-soft)]">
      Machine hors ligne — les sessions sont lues sur le PC agent.
    </p>

    <template v-else>
      <USelectMenu
        :model-value="modelValue"
        :items="options"
        value-key="session_id"
        label-key="label"
        searchable
        placeholder="Nouvelle session (pas de reprise)"
        class="w-full"
        :ui="{ content: 'z-[60]' }"
        @update:model-value="onSelect"
      />

      <p v-if="modelValue && !compact" class="mt-2 text-xs text-[var(--app-ink-soft)]">
        Le message sera envoyé dans cette session avec
        <span class="font-medium text-[var(--app-accent-ink)]">« Vas-y, continue »</span>
        si le champ est vide.
      </p>
    </template>
  </div>
</template>

<script lang="ts" setup>
import { computed, ref, watch } from 'vue'
import type { ClaudeSession } from '~/types'
import { listClaudeSessions } from '~/services/machinesService'

/**
 * Picker for resuming an existing Claude Code session on the target machine.
 */
const props = defineProps<{
  machineId?: number
  localPath?: string | null
  offline?: boolean
  modelValue: string | null
  compact?: boolean
}>()

const emit = defineEmits<{
  'update:modelValue': [value: string | null]
  select: [session: ClaudeSession | null]
}>()

const loading = ref(false)
const sessions = ref<ClaudeSession[]>([])

const options = computed(() =>
  sessions.value.map((session) => ({
    session_id: session.session_id,
    label: session.title
      ? `${session.title} · ${formatRelative(session.updated_at)}`
      : `${session.session_id.slice(0, 8)}… · ${formatRelative(session.updated_at)}`,
    session,
  })),
)

/**
 * Load sessions when machine/path changes.
 */
async function refresh(): Promise<void> {
  if (!props.machineId || !props.localPath?.trim() || props.offline) {
    sessions.value = []
    return
  }
  loading.value = true
  try {
    const response = await listClaudeSessions(props.machineId, props.localPath.trim())
    sessions.value = response.sessions
  } catch {
    sessions.value = []
  } finally {
    loading.value = false
  }
}

/**
 * Handle session selection from the menu.
 * @param value - Selected session id or null.
 */
function onSelect(value: string | null): void {
  emit('update:modelValue', value)
  const session = sessions.value.find((item) => item.session_id === value) ?? null
  emit('select', session)
}

/**
 * Format a timestamp as a short relative label.
 * @param iso - ISO timestamp.
 * @returns Human label.
 */
function formatRelative(iso: string): string {
  const diffMs = Date.now() - new Date(iso).getTime()
  const minutes = Math.round(diffMs / 60000)
  if (minutes < 60) {
    return `il y a ${Math.max(1, minutes)} min`
  }
  const hours = Math.round(minutes / 60)
  if (hours < 48) {
    return `il y a ${hours} h`
  }
  return new Date(iso).toLocaleDateString('fr-FR', { day: 'numeric', month: 'short' })
}

watch(
  () => [props.machineId, props.localPath, props.offline] as const,
  () => {
    refresh()
  },
  { immediate: true },
)
</script>
