import { watch } from 'vue'
import { isPushDisabledLocally, isPushSupported, subscribeToPush } from '~/utils/webPush'

/**
 * Auto-subscribe to push once permission is granted (so notifications stay "on by default"),
 * unless the user turned them off on this device. First-time permission still needs the
 * dashboard switch (an iOS user gesture requirement).
 */
export default defineNuxtPlugin(() => {
  const userStore = useUserStore()

  /**
   * Whether we're running inside the Tauri desktop shell (web push is PWA-only there).
   * @returns True on the desktop build.
   */
  function isDesktopApp(): boolean {
    const w = window as Window & { __TAURI__?: unknown; __TAURI_INTERNALS__?: unknown }
    return Boolean(w.__TAURI__ || w.__TAURI_INTERNALS__)
  }

  /**
   * Ensure a fresh push subscription exists when eligible.
   * @returns Nothing.
   */
  async function ensureSubscribed(): Promise<void> {
    if (isDesktopApp() || !isPushSupported() || isPushDisabledLocally()) {
      return
    }
    if (Notification.permission !== 'granted' || !userStore.token) {
      return
    }
    await subscribeToPush().catch(() => {})
  }

  void ensureSubscribed()
  watch(
    () => userStore.token,
    () => {
      void ensureSubscribed()
    },
  )
})
