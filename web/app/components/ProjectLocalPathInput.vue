<template>
  <div class="flex flex-col gap-1.5">
    <label class="text-sm font-medium text-[var(--app-ink)]">
      Chemin local{{ machineName ? ` sur ${machineName}` : '' }}
    </label>
    <UInput
      :model-value="modelValue"
      class="w-full"
      size="lg"
      :required="required"
      :autofocus="autofocus"
      :placeholder="placeholder"
      :disabled="disabled"
      @update:model-value="emit('update:modelValue', $event)"
      @blur="emit('blur')"
    >
      <template #trailing>
        <UButton
          type="button"
          color="neutral"
          variant="ghost"
          icon="i-lucide-folder-open"
          size="sm"
          :disabled="disabled || picking"
          :loading="picking"
          title="Parcourir…"
          aria-label="Parcourir…"
          @click.stop.prevent="pickFolder"
        />
      </template>
    </UInput>
  </div>
</template>

<script lang="ts" setup>
import { ref } from 'vue'

/**
 * Local project path input with native folder picker (desktop).
 */
const props = withDefaults(
  defineProps<{
    modelValue: string
    machineName?: string
    disabled?: boolean
    required?: boolean
    autofocus?: boolean
    placeholder?: string
  }>(),
  {
    machineName: undefined,
    disabled: false,
    required: false,
    autofocus: false,
    placeholder: 'C:\\Users\\moi\\Projects\\mon-projet',
  },
)

const emit = defineEmits<{
  'update:modelValue': [value: string]
  blur: []
}>()

const toast = useToast()
const { isDesktopApp } = useDesktopRuntime()
const picking = ref(false)

/**
 * Open the native folder picker (Tauri desktop) and fill the path.
 * @returns Nothing.
 */
async function pickFolder(): Promise<void> {
  if (props.disabled || picking.value) {
    return
  }
  if (!isDesktopApp.value) {
    toast.add({
      title: 'Parcourir disponible dans l’app desktop',
      description: 'Colle le chemin du dossier, ou ouvre NightForge en desktop.',
      color: 'neutral',
    })
    return
  }
  picking.value = true
  try {
    const { invoke } = await import('@tauri-apps/api/core')
    const selected = await invoke<string | null>('pick_project_folder')
    if (typeof selected === 'string' && selected.trim()) {
      emit('update:modelValue', selected)
      emit('blur')
    }
  } catch (err) {
    const detail = err instanceof Error ? err.message : String(err ?? '')
    toast.add({
      title: 'Impossible d’ouvrir l’explorateur',
      description: detail || 'Relance l’app desktop (tauri:dev) pour charger le dialogue natif.',
      color: 'error',
    })
  } finally {
    picking.value = false
  }
}
</script>
