<template>
  <Transition
    enter-active-class="transition duration-300 ease-out"
    enter-from-class="-translate-y-full opacity-0"
    enter-to-class="translate-y-0 opacity-100"
    leave-active-class="transition duration-200 ease-in"
    leave-from-class="translate-y-0 opacity-100"
    leave-to-class="-translate-y-full opacity-0"
  >
    <div v-if="showBanner" class="fixed inset-x-0 top-0 z-[110] px-3 pt-[max(0.5rem,env(safe-area-inset-top))]">
      <div
        class="mx-auto flex max-w-2xl items-center gap-2.5 rounded-xl border border-[var(--app-line)] bg-[var(--app-surface)] px-3 py-2.5 shadow-[var(--app-shadow-soft)]"
      >
        <UIcon name="i-lucide-sparkles" class="h-4 w-4 shrink-0 text-[var(--app-accent-ink)]" />
        <span class="min-w-0 flex-1 truncate text-sm font-medium text-[var(--app-ink)]">
          {{ t('update.available') }}
        </span>
        <UButton size="xs" color="primary" @click="reload">{{ t('update.reload') }}</UButton>
        <button
          type="button"
          class="flex h-7 w-7 shrink-0 items-center justify-center rounded-md text-[var(--app-ink-soft)] transition-colors hover:bg-[var(--app-surface-2)] hover:text-[var(--app-ink)]"
          :aria-label="t('common.close')"
          @click="dismiss"
        >
          <UIcon name="i-lucide-x" class="h-4 w-4" />
        </button>
      </div>
    </div>
  </Transition>
</template>

<script lang="ts" setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'

/**
 * Web update banner — an iOS home-screen PWA never reloads on its own, so we poll the
 * server's build id and offer a reload when a new version has been deployed. Desktop is
 * excluded (it has the Tauri auto-updater).
 */
const { t } = useI18n()

const config = useRuntimeConfig()
const loadedBuildId = String(config.public.buildId ?? '')
const isDesktop = Boolean(config.public.isDesktop)

const latestBuildId = ref(loadedBuildId)
const dismissedBuildId = ref<string | null>(null)
let timer: ReturnType<typeof setInterval> | null = null

const showBanner = computed(
  () =>
    !isDesktop &&
    Boolean(loadedBuildId) &&
    latestBuildId.value !== loadedBuildId &&
    latestBuildId.value !== dismissedBuildId.value,
)

/**
 * Fetch the running server's build id to detect a new deployment.
 * @returns Nothing.
 */
async function check(): Promise<void> {
  try {
    const response = await $fetch<{ buildId?: string }>('/_app-version')
    if (response?.buildId) {
      latestBuildId.value = String(response.buildId)
    }
  } catch {
    // Offline or transient — keep the current known version.
  }
}

/**
 * Hard-reload the app to load the freshly deployed version.
 * @returns Nothing.
 */
function reload(): void {
  reloadNuxtApp({ force: true })
}

/**
 * Dismiss the banner for the current version (re-shows only if a newer one ships).
 * @returns Nothing.
 */
function dismiss(): void {
  dismissedBuildId.value = latestBuildId.value
}

onMounted(() => {
  if (isDesktop) {
    return
  }
  timer = setInterval(check, 30000)
})

onBeforeUnmount(() => {
  if (timer) clearInterval(timer)
})
</script>
