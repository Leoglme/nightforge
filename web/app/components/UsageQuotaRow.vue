<template>
  <li>
    <div class="mb-1 flex items-center justify-between gap-2 text-sm">
      <span>{{ label }}</span>
      <span class="font-medium text-[var(--app-ink)] tabular-nums">{{ pct }}</span>
    </div>
    <div class="h-2 overflow-hidden rounded-full bg-[var(--app-line)]">
      <div class="h-full rounded-full transition-all" :class="barClass" :style="{ width: `${width}%` }" />
    </div>
  </li>
</template>

<script lang="ts" setup>
import { computed } from 'vue'

const props = defineProps<{
  label: string
  utilization: number
}>()

const width = computed(() => Math.round(Math.max(0, Math.min(1, props.utilization)) * 100))

const pct = computed(() => `${width.value} %`)

const barClass = computed(() => {
  if (props.utilization >= 0.85) return 'bg-red-500'
  if (props.utilization >= 0.6) return 'bg-amber-500'
  return 'bg-blue-500'
})
</script>
