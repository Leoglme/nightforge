/**
 * Desktop-only: reconnect the bundled agent on startup when this PC is already provisioned.
 *
 * After an app update the sidecar may have been killed by the installer; this ensures
 * `~/.nightforge/agent.json` is picked up and the machine shows online without manual action.
 */
export default defineNuxtPlugin(() => {
  const { isDesktopApp } = useDesktopRuntime()
  if (!isDesktopApp.value) {
    return
  }

  const { syncLocalAgentIfProvisioned, readProvisionFile } = useMachineProvision()

  void (async () => {
    const provisioned = await readProvisionFile()
    if (!provisioned?.agent_token?.trim()) {
      return
    }

    const afterUpdate = window.sessionStorage.getItem('nightforge-force-agent-sync') === '1'
    if (afterUpdate) {
      window.sessionStorage.removeItem('nightforge-force-agent-sync')
    }

    // Let Tauri `setup()` finish its first spawn, then force a reconnect with fresh config.
    await new Promise((resolve) => setTimeout(resolve, afterUpdate ? 600 : 1200))
    await syncLocalAgentIfProvisioned()
  })()
})
