<template>
  <ChatComposer
    :text="text"
    :provider="provider"
    :model="model"
    :effort="effort"
    :fast-mode="fastMode"
    :project-id="projectId"
    :project-options="projectOptions"
    :can-send="canSend"
    :loading="loading"
    @update:text="emit('update:text', $event)"
    @update:provider="emit('update:provider', $event)"
    @update:model="emit('update:model', $event)"
    @update:effort="emit('update:effort', $event)"
    @update:fast-mode="emit('update:fastMode', $event)"
    @update:project-id="emit('update:projectId', $event)"
    @send="emit('send')"
  />
</template>

<script lang="ts" setup>
import type { AiProvider } from '~/constants/modelPresets'

/**
 * Thin alias kept for the run detail page — shared UI lives in ChatComposer.
 */
defineProps<{
  text: string
  provider: AiProvider | null
  model: string | null
  effort: string | null
  fastMode: boolean
  projectId?: number
  projectOptions: { label: string; value: number }[]
  canSend: boolean
  loading?: boolean
}>()

const emit = defineEmits<{
  'update:text': [value: string]
  'update:provider': [value: AiProvider | null]
  'update:model': [value: string | null]
  'update:effort': [value: string | null]
  'update:fastMode': [value: boolean]
  'update:projectId': [value: number | undefined]
  send: []
}>()
</script>
