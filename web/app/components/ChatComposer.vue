<template>
  <div :class="fullWidth ? 'w-full' : 'mx-auto w-full max-w-4xl xl:max-w-5xl'">
    <UFormField v-if="projectOptions.length > 1" :label="t('runs.chat.project')" class="mb-2.5">
      <USelectMenu
        :model-value="projectId"
        :items="projectOptions"
        value-key="value"
        label-key="label"
        class="w-full"
        @update:model-value="emit('update:projectId', $event)"
      />
    </UFormField>

    <!-- Attached images (mobile PWA) — compressed thumbnails with remove -->
    <div v-if="attachments.length" class="mb-2 flex flex-wrap gap-2">
      <div
        v-for="image in attachments"
        :key="image.id"
        class="relative h-16 w-16 overflow-hidden rounded-xl border border-[var(--app-line)] bg-[var(--app-surface-2)]"
      >
        <img :src="image.dataUrl" :alt="image.name" class="h-full w-full object-cover" />
        <button
          type="button"
          class="absolute top-0.5 right-0.5 flex h-5 w-5 cursor-pointer items-center justify-center rounded-full bg-[var(--app-ink)]/85 text-[var(--app-surface)] transition-opacity hover:opacity-80"
          :aria-label="t('runs.chat.removeImage')"
          @click="removeAttachment(image.id)"
        >
          <UIcon name="i-lucide-x" class="h-3 w-3" />
        </button>
      </div>
    </div>

    <div
      class="relative rounded-2xl border border-[var(--app-line)] bg-[var(--app-surface-2)] transition-[border-color] duration-200 focus-within:border-[var(--app-ink-soft)]"
    >
      <textarea
        ref="inputEl"
        :value="text"
        rows="1"
        :placeholder="placeholder || t('runs.chat.placeholder')"
        class="max-h-48 min-h-[2.5rem] w-full resize-none overflow-y-auto bg-transparent py-2.5 pr-12 pl-3.5 text-base leading-normal text-[var(--app-ink)] outline-none placeholder:text-[var(--app-ink-soft)] sm:min-h-[2.625rem] sm:py-2.5 sm:pr-12 sm:pl-4"
        @input="onInput"
        @keydown.enter.exact.prevent="trySend"
      />
      <button
        type="button"
        class="absolute right-2 bottom-1.5 flex h-8 w-8 cursor-pointer items-center justify-center rounded-lg transition-all duration-200 disabled:cursor-not-allowed sm:right-2.5 sm:bottom-2"
        :class="
          hasContent
            ? 'bg-[var(--app-ink)] text-[var(--app-surface)] hover:opacity-90'
            : 'bg-transparent text-[var(--app-ink-soft)] opacity-35'
        "
        :disabled="!hasContent || loading"
        :aria-label="t('runs.chat.send')"
        @click="trySend"
      >
        <UIcon
          :name="loading ? 'i-lucide-loader-circle' : 'i-lucide-corner-down-left'"
          :class="['h-3.5 w-3.5', loading ? 'animate-spin' : '']"
        />
      </button>
    </div>

    <div class="mt-2 flex flex-wrap items-center gap-2">
      <UPopover v-if="allowImages" v-model:open="pickerOpen" :ui="{ content: 'p-0 w-[min(14rem,calc(100vw-1.5rem))]' }">
        <button
          type="button"
          class="flex h-8 w-8 shrink-0 cursor-pointer items-center justify-center rounded-full border border-[var(--app-line)] text-[var(--app-ink)] transition-colors hover:bg-[var(--app-surface-2)]"
          :aria-label="t('runs.chat.addImage')"
        >
          <UIcon name="i-lucide-plus" class="h-4 w-4" />
        </button>

        <template #content>
          <div class="flex flex-col py-1.5">
            <button
              type="button"
              class="flex w-full cursor-pointer items-center gap-2.5 px-3 py-2.5 text-left text-sm text-[var(--app-ink)] transition-colors hover:bg-[var(--app-surface-2)]"
              @click="openCamera"
            >
              <UIcon name="i-lucide-camera" class="h-4 w-4 shrink-0 text-[var(--app-ink-soft)]" />
              {{ t('runs.chat.takePhoto') }}
            </button>
            <button
              type="button"
              class="flex w-full cursor-pointer items-center gap-2.5 px-3 py-2.5 text-left text-sm text-[var(--app-ink)] transition-colors hover:bg-[var(--app-surface-2)]"
              @click="openLibrary"
            >
              <UIcon name="i-lucide-image" class="h-4 w-4 shrink-0 text-[var(--app-ink-soft)]" />
              {{ t('runs.chat.photoLibrary') }}
            </button>
          </div>
        </template>
      </UPopover>

      <div v-if="hint || showContinue" class="flex min-w-0 flex-1 flex-wrap items-center gap-1">
        <p v-if="hint" class="text-xs text-[var(--app-ink-soft)]">{{ hint }}</p>
        <UButton
          v-if="showContinue"
          size="xs"
          color="neutral"
          variant="ghost"
          icon="i-lucide-play"
          @click="emit('continue')"
        >
          {{ continueLabel || t('compose.continue') }}
        </UButton>
      </div>
      <ChatModelControls
        class="ml-auto"
        :provider="provider"
        :model="model"
        :effort="effort"
        :fast-mode="fastMode"
        @update:provider="emit('update:provider', $event)"
        @update:model="emit('update:model', $event)"
        @update:effort="emit('update:effort', $event)"
        @update:fast-mode="emit('update:fastMode', $event)"
      >
        <template v-if="$slots.controlsStart" #start>
          <slot name="controlsStart" />
        </template>
      </ChatModelControls>
    </div>

    <input
      v-if="allowImages"
      ref="cameraInput"
      type="file"
      accept="image/*"
      capture="environment"
      class="hidden"
      @change="onFilesPicked"
    />
    <input
      v-if="allowImages"
      ref="libraryInput"
      type="file"
      accept="image/*"
      multiple
      class="hidden"
      @change="onFilesPicked"
    />
  </div>
</template>

<script lang="ts" setup>
import { computed, nextTick, ref } from 'vue'
import type { AiProvider } from '~/constants/modelPresets'
import type { ComposerImage } from '~/types'
import { compressImageFile } from '~/utils/imageCompression'

/**
 * Shared Claude Code–style chat composer (run page + Compose + PC session).
 */
const props = withDefaults(
  defineProps<{
    text: string
    provider: AiProvider | null
    model: string | null
    effort: string | null
    fastMode: boolean
    projectId?: number
    projectOptions?: { label: string; value: number }[]
    canSend: boolean
    loading?: boolean
    placeholder?: string
    hint?: string | null
    showContinue?: boolean
    continueLabel?: string
    /** Skip max-width centering (Compose column already constrains width). */
    fullWidth?: boolean
    /** Show the « + » image picker (mobile PWA image send). */
    allowImages?: boolean
  }>(),
  {
    projectOptions: () => [],
    loading: false,
    showContinue: false,
    fullWidth: false,
    allowImages: false,
  },
)

const emit = defineEmits<{
  'update:text': [value: string]
  'update:provider': [value: AiProvider | null]
  'update:model': [value: string | null]
  'update:effort': [value: string | null]
  'update:fastMode': [value: boolean]
  'update:projectId': [value: number | undefined]
  send: [images: ComposerImage[]]
  continue: []
}>()

/** Upper bound on attachments per message (mirrors the native picker). */
const MAX_IMAGES = 5

const { t } = useI18n()
const inputEl = ref<HTMLTextAreaElement | null>(null)
const cameraInput = ref<HTMLInputElement | null>(null)
const libraryInput = ref<HTMLInputElement | null>(null)
const pickerOpen = ref(false)
const attachments = ref<ComposerImage[]>([])

/** Sendable when there is text or at least one attached image. */
const hasContent = computed(() => props.canSend || attachments.value.length > 0)

/**
 * Grow the textarea with content (capped via CSS max-height).
 */
function onInput(event: Event): void {
  const el = event.target as HTMLTextAreaElement
  emit('update:text', el.value)
  el.style.height = '0px'
  el.style.height = `${Math.min(Math.max(el.scrollHeight, 40), 192)}px`
}

/**
 * Open the camera capture input (direct photo).
 */
function openCamera(): void {
  pickerOpen.value = false
  cameraInput.value?.click()
}

/**
 * Open the photo-library / files input (native OS picker).
 */
function openLibrary(): void {
  pickerOpen.value = false
  libraryInput.value?.click()
}

/**
 * Compress each picked file and add it to the attachments (up to the cap).
 * @param event - The file input change event.
 * @returns Nothing.
 */
async function onFilesPicked(event: Event): Promise<void> {
  const input = event.target as HTMLInputElement
  const files = Array.from(input.files ?? [])
  input.value = ''
  for (const file of files) {
    if (attachments.value.length >= MAX_IMAGES) {
      break
    }
    try {
      attachments.value.push(await compressImageFile(file))
    } catch {
      // Skip files the browser cannot decode (unsupported format, corrupt).
    }
  }
}

/**
 * Remove one attached image.
 * @param id - The attachment id to drop.
 */
function removeAttachment(id: string): void {
  attachments.value = attachments.value.filter((image) => image.id !== id)
}

/**
 * Send the message with its attachments, then clear the picker state.
 */
function trySend(): void {
  if (!hasContent.value || props.loading) {
    return
  }
  emit('send', attachments.value.slice())
  attachments.value = []
  nextTick(() => {
    if (inputEl.value) {
      inputEl.value.style.height = ''
    }
  })
}
</script>
