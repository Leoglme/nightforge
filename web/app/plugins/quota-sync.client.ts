/**
 * Desktop: periodically sync Claude/Cursor quotas while the app is open, and force a
 * final persist when the window is hidden or closing — so mobile/web keep last readings.
 */
export default defineNuxtPlugin(() => {
  const { isDesktopApp } = useDesktopRuntime()
  if (!isDesktopApp.value) {
    return
  }

  const usageStore = useUsageStore()
  let timer: ReturnType<typeof setInterval> | null = null
  let syncing = false

  /**
   * Best-effort live read → API snapshots (ignore errors — agent may be offline).
   */
  async function syncQuotas(): Promise<void> {
    if (syncing) {
      return
    }
    syncing = true
    try {
      await usageStore.refresh()
    } catch {
      // Non-fatal: heartbeat still pushes quotas when the agent is connected.
    } finally {
      syncing = false
    }
  }

  /**
   * Persist quotas when the desktop window is backgrounded.
   */
  function onVisibilityChange(): void {
    if (document.visibilityState === 'hidden') {
      void syncQuotas()
    }
  }

  /**
   * Persist quotas on page unload / app close.
   */
  function onPageHide(): void {
    void syncQuotas()
  }

  // First sync shortly after boot (agent sidecar may still be connecting).
  void (async () => {
    await new Promise((resolve) => setTimeout(resolve, 2500))
    await syncQuotas()
  })()

  // Keep snapshots fresh while the desktop app stays open (~2 min).
  timer = setInterval(() => {
    void syncQuotas()
  }, 120_000)

  document.addEventListener('visibilitychange', onVisibilityChange)
  window.addEventListener('pagehide', onPageHide)

  if (import.meta.hot) {
    import.meta.hot.dispose(() => {
      if (timer) {
        clearInterval(timer)
      }
      document.removeEventListener('visibilitychange', onVisibilityChange)
      window.removeEventListener('pagehide', onPageHide)
    })
  }
})
