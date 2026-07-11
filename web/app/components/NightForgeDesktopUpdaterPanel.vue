<template>
  <Transition
    enter-active-class="transition duration-300 ease-out"
    enter-from-class="opacity-0"
    enter-to-class="opacity-100"
    leave-active-class="transition duration-200 ease-in"
    leave-from-class="opacity-100"
    leave-to-class="opacity-0"
  >
    <div
      v-if="visible"
      class="fixed inset-0 z-[100] flex items-center justify-center bg-[var(--app-overlay)] p-4 backdrop-blur-md"
      @click.self="closePanel"
    >
      <div
        class="relative w-full max-w-lg overflow-hidden rounded-2xl border border-[var(--app-line)] bg-[var(--app-surface)] p-6 sm:p-8"
      >
        <div class="space-y-6">
          <div class="flex flex-col gap-4 sm:flex-row sm:items-start sm:justify-between">
            <div class="min-w-0 space-y-2">
              <p class="text-xs font-semibold tracking-[0.12em] text-[var(--app-accent-ink)] uppercase">Mise à jour</p>
              <h2 class="text-xl font-semibold text-[var(--app-ink)] sm:text-2xl">{{ statusTitle }}</h2>
              <p class="text-sm leading-relaxed text-[var(--app-ink-soft)]">{{ statusDescription }}</p>
            </div>
            <div v-if="currentVersion || nextVersion" class="flex shrink-0 flex-wrap items-center gap-2">
              <span
                v-if="currentVersion"
                class="rounded-md bg-[var(--app-surface-2)] px-2 py-1 font-mono text-xs text-[var(--app-ink-soft)]"
              >
                v{{ currentVersion }}
              </span>
              <span v-if="currentVersion && nextVersion" class="text-[var(--app-ink-soft)]">→</span>
              <span
                v-if="nextVersion"
                class="rounded-md bg-[var(--app-accent-soft)] px-2 py-1 font-mono text-xs text-[var(--app-accent-ink)]"
              >
                v{{ nextVersion }}
              </span>
            </div>
          </div>

          <div v-if="status === 'downloading'" class="space-y-3">
            <div class="flex items-center justify-between gap-3 text-xs">
              <span class="font-medium text-[var(--app-ink)] tabular-nums">{{ downloadLabel }}</span>
              <span v-if="totalBytes && totalBytes > 0" class="text-[var(--app-ink-soft)] tabular-nums">
                {{ (downloadedBytes / (1024 * 1024)).toFixed(1) }} / {{ (totalBytes / (1024 * 1024)).toFixed(1) }} Mo
              </span>
            </div>
            <div v-if="downloadPercent != null" class="h-2 overflow-hidden rounded-full bg-[var(--app-surface-2)]">
              <div
                class="h-full rounded-full bg-[var(--app-accent)] transition-all"
                :style="{ width: `${downloadPercent}%` }"
              />
            </div>
          </div>

          <div class="flex flex-wrap justify-end gap-3">
            <UButton v-if="canDismiss" color="neutral" variant="outline" @click="closePanel">Plus tard</UButton>
            <UButton v-if="status === 'available'" color="primary" @click="installUpdate">Installer</UButton>
            <UButton v-if="status === 'installed'" color="primary" @click="restartApp">Redémarrer</UButton>
            <UButton v-if="status === 'error'" color="primary" @click="installUpdate">Réessayer</UButton>
          </div>
        </div>
      </div>
    </div>
  </Transition>
</template>

<script lang="ts" setup>
import { computed, onMounted, ref, shallowRef } from 'vue'
import type { DownloadEvent, Update } from '@tauri-apps/plugin-updater'
import type { NightForgeUpdaterStatus } from '~/types/NightForgeDesktopUpdaterPanel'
import { invoke } from '@tauri-apps/api/core'
import { check } from '@tauri-apps/plugin-updater'
import { relaunch } from '@tauri-apps/plugin-process'

const { isProdDesktop } = useDesktopRuntime()

const visible = ref(false)
const status = ref<NightForgeUpdaterStatus>('idle')
const currentVersion = ref<string | null>(null)
const nextVersion = ref<string | null>(null)
const errorMessage = ref<string | null>(null)
const pendingUpdate = shallowRef<Update | null>(null)
const downloadedBytes = ref(0)
const totalBytes = ref<number | null>(null)

const downloadPercent = computed(() => {
  const total = totalBytes.value
  if (total == null || total <= 0) {
    return null
  }
  return Math.min(100, Math.round((100 * downloadedBytes.value) / total))
})

const downloadLabel = computed(() => {
  if (status.value !== 'downloading') {
    return ''
  }
  const pct = downloadPercent.value
  if (pct != null) {
    return `${pct}%`
  }
  if (downloadedBytes.value > 0) {
    return `${(downloadedBytes.value / (1024 * 1024)).toFixed(1)} Mo téléchargés`
  }
  return 'Préparation du téléchargement…'
})

const canDismiss = computed(() => status.value === 'available' || status.value === 'error')

const statusTitle = computed(() => {
  if (status.value === 'available') return 'Mise à jour disponible'
  if (status.value === 'downloading') return 'Téléchargement en cours'
  if (status.value === 'installed') return 'Mise à jour installée'
  if (status.value === 'error') return 'Échec de la mise à jour'
  return 'Mise à jour'
})

const statusDescription = computed(() => {
  if (status.value === 'available') {
    if (nextVersion.value && currentVersion.value) {
      return `Passe de la v${currentVersion.value} à la v${nextVersion.value}. L'app va se fermer brièvement pour terminer l'installation.`
    }
    return 'Une nouvelle version est prête. L\u2019app va se fermer brièvement pour terminer l\u2019installation.'
  }
  if (status.value === 'downloading') {
    return 'Ne ferme pas NightForge pendant cette étape.'
  }
  if (status.value === 'installed') {
    return 'Redémarre NightForge pour charger la nouvelle version. Tes données sont conservées.'
  }
  if (status.value === 'error') {
    return (
      errorMessage.value ||
      'Une erreur est survenue pendant la mise à jour. Ferme NightForge, vérifie que nightforge-agent.exe n\u2019est plus dans le Gestionnaire des tâches, puis réessaie.'
    )
  }
  return ''
})

function resetDownloadProgress(): void {
  downloadedBytes.value = 0
  totalBytes.value = null
}

function onDownloadEvent(event: DownloadEvent): void {
  if (event.event === 'Started') {
    const len = event.data.contentLength
    totalBytes.value = len != null && len > 0 ? len : null
    downloadedBytes.value = 0
  } else if (event.event === 'Progress') {
    downloadedBytes.value += event.data.chunkLength
  }
}

function closePanel(): void {
  if (!canDismiss.value) {
    return
  }
  visible.value = false
}

async function installUpdate(): Promise<void> {
  if (!pendingUpdate.value) {
    return
  }
  try {
    status.value = 'downloading'
    errorMessage.value = null
    resetDownloadProgress()
    // Release nightforge-agent.exe so the NSIS installer can overwrite it.
    await invoke('prepare_desktop_update')
    await pendingUpdate.value.downloadAndInstall(onDownloadEvent)
    status.value = 'installed'
  } catch (error) {
    status.value = 'error'
    errorMessage.value = error instanceof Error ? error.message : 'Téléchargement ou installation impossible.'
  }
}

async function restartApp(): Promise<void> {
  try {
    window.sessionStorage.setItem('nightforge-force-agent-sync', '1')
    await relaunch()
  } catch (error) {
    console.error('[Updater] relaunch failed:', error)
    window.location.reload()
  }
}

async function checkForUpdate(): Promise<void> {
  if (!import.meta.client || !isProdDesktop.value) {
    return
  }
  if (window.sessionStorage.getItem('nightforge-updater-checked') === '1') {
    return
  }
  window.sessionStorage.setItem('nightforge-updater-checked', '1')

  errorMessage.value = null
  resetDownloadProgress()

  try {
    const update = await check()
    pendingUpdate.value = update
    if (!update) {
      status.value = 'idle'
      return
    }
    currentVersion.value = update.currentVersion || null
    nextVersion.value = update.version || null
    status.value = 'available'
    visible.value = true
  } catch (error) {
    console.error('[Updater] silent check failed:', error)
    status.value = 'idle'
    pendingUpdate.value = null
  }
}

onMounted(() => {
  void checkForUpdate()
})
</script>
