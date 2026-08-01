<template>
  <div class="relative">
    <select
      :value="modelValue === null || modelValue === undefined ? '' : String(modelValue)"
      :disabled="disabled"
      class="w-full cursor-pointer appearance-none rounded-lg border border-[var(--app-line)] bg-[var(--app-surface-2)] py-2.5 pr-9 pl-3 text-sm text-[var(--app-ink)] transition-colors outline-none focus:border-[var(--app-ink-soft)] disabled:cursor-not-allowed disabled:opacity-50"
      @change="onChange"
    >
      <option v-if="placeholder" value="" disabled>{{ placeholder }}</option>
      <option v-for="item in items" :key="String(item.value)" :value="String(item.value)">
        {{ item.label }}
      </option>
    </select>
    <UIcon
      name="i-lucide-chevron-down"
      class="pointer-events-none absolute top-1/2 right-3 h-4 w-4 -translate-y-1/2 text-[var(--app-ink-soft)]"
      aria-hidden="true"
    />
  </div>
</template>

<script lang="ts" setup>
/**
 * Styled native `<select>` — triggers the OS picker (iOS wheel) instead of a
 * searchable combobox, so mobile never auto-focuses a search input and scrolls.
 */
const props = defineProps<{
  modelValue: string | number | null | undefined
  items: { label: string; value: string | number }[]
  placeholder?: string
  disabled?: boolean
}>()

const emit = defineEmits<{
  'update:modelValue': [value: string | number | null]
}>()

/**
 * Emit the original typed value matching the picked option.
 * @param event - The native change event.
 * @returns Nothing.
 */
function onChange(event: Event): void {
  const raw = (event.target as HTMLSelectElement).value
  const match = props.items.find((item) => String(item.value) === raw)
  emit('update:modelValue', match ? match.value : null)
}
</script>
