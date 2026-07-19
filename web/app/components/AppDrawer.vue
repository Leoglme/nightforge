<template>
  <Teleport to="body">
    <Transition name="app-drawer-backdrop">
      <div v-if="open" class="fixed inset-0 z-40 bg-[var(--app-overlay)] backdrop-blur-sm" @click="emit('close')" />
    </Transition>

    <Transition name="app-drawer-panel">
      <div
        v-if="open"
        class="fixed top-0 right-0 z-50 flex h-dvh w-full max-w-[460px] flex-col border-l border-[var(--app-line)] bg-[var(--app-surface)] shadow-2xl"
        role="dialog"
        aria-modal="true"
      >
        <!-- Header -->
        <div class="flex items-start gap-3 border-b border-[var(--app-line)] px-4 py-4 sm:px-5">
          <button
            v-if="showBack"
            type="button"
            class="flex h-10 w-7 shrink-0 items-center justify-center rounded text-[var(--app-ink-soft)] transition-colors hover:bg-[var(--app-surface-2)] hover:text-[var(--app-ink)]"
            aria-label="Retour"
            @click="emit('back')"
          >
            <UIcon name="i-lucide-chevron-left" class="h-4 w-4" />
          </button>

          <span
            v-if="icon || $slots.icon"
            class="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg border border-[var(--app-line)] bg-[var(--app-surface-2)]"
          >
            <slot name="icon">
              <UIcon v-if="icon" :name="icon" class="h-4 w-4 text-[var(--app-ink-soft)]" />
            </slot>
          </span>

          <div class="min-w-0 flex-1">
            <h2 class="text-base leading-tight font-semibold text-[var(--app-ink)]">{{ title }}</h2>
            <p v-if="subtitle" class="mt-0.5 truncate text-[11px] text-[var(--app-ink-soft)]">{{ subtitle }}</p>
          </div>

          <button
            type="button"
            class="flex h-7 w-7 shrink-0 items-center justify-center rounded text-[var(--app-ink-soft)] transition-colors hover:bg-[var(--app-surface-2)] hover:text-[var(--app-ink)]"
            aria-label="Fermer"
            @click="emit('close')"
          >
            <UIcon name="i-lucide-x" class="h-4 w-4" />
          </button>
        </div>

        <!-- Body: overflow-visible so SelectMenu portals aren't clipped -->
        <div class="min-h-0 flex-1 overflow-x-visible overflow-y-auto px-4 py-4 sm:px-5">
          <slot />
        </div>

        <!-- Footer -->
        <div v-if="$slots.footer" class="flex gap-2 border-t border-[var(--app-line)] px-4 py-4 sm:px-5">
          <slot name="footer" />
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<script lang="ts" setup>
import { onBeforeUnmount, onMounted, watch } from 'vue'

/**
 * Reusable right-side drawer (slide-in panel), mirroring the DevLeadHunter UX:
 * full-width on mobile, capped panel on desktop, backdrop + Esc to close.
 */
const props = withDefaults(
  defineProps<{
    open: boolean
    title: string
    subtitle?: string
    icon?: string
    showBack?: boolean
  }>(),
  {
    subtitle: undefined,
    icon: undefined,
    showBack: false,
  },
)

const emit = defineEmits<{
  close: []
  back: []
}>()

/**
 * Close the drawer on Escape.
 * @param event - Keyboard event.
 * @returns Nothing.
 */
function onKeydown(event: KeyboardEvent): void {
  if (event.key === 'Escape' && props.open) {
    emit('close')
  }
}

watch(
  () => props.open,
  (open) => {
    if (import.meta.client) {
      document.body.style.overflow = open ? 'hidden' : ''
    }
  },
)

onMounted(() => {
  window.addEventListener('keydown', onKeydown)
})

onBeforeUnmount(() => {
  window.removeEventListener('keydown', onKeydown)
  if (import.meta.client) {
    document.body.style.overflow = ''
  }
})
</script>

<style scoped>
.app-drawer-panel-enter-active,
.app-drawer-panel-leave-active {
  transition: transform 0.25s cubic-bezier(0.4, 0, 0.2, 1);
}
.app-drawer-panel-enter-from,
.app-drawer-panel-leave-to {
  transform: translateX(100%);
}

.app-drawer-backdrop-enter-active,
.app-drawer-backdrop-leave-active {
  transition: opacity 0.25s ease;
}
.app-drawer-backdrop-enter-from,
.app-drawer-backdrop-leave-to {
  opacity: 0;
}

@media (prefers-reduced-motion: reduce) {
  .app-drawer-panel-enter-active,
  .app-drawer-panel-leave-active,
  .app-drawer-backdrop-enter-active,
  .app-drawer-backdrop-leave-active {
    transition: none;
  }
}
</style>
