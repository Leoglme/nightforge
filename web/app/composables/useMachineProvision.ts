import type { MachineCreated } from '~/types'
import { createMachine, listMachines, reissueMachineToken } from '~/services/machinesService'

/**
 * Path of the shared provisioning file, relative to the user's home directory.
 * Must stay in sync with the agent (`nightforge_agent.config.PROVISION_PATH`).
 */
const PROVISION_DIR = '.nightforge'
const PROVISION_FILE = `${PROVISION_DIR}/agent.json`

/**
 * One-click machine provisioning for the desktop app.
 *
 * In the packaged Tauri app the agent runs as a bundled sidecar; the only missing piece is
 * the token. This composable registers the current machine against the control-plane and
 * writes `~/.nightforge/agent.json`, which the agent picks up automatically — no manual
 * `.env` editing. In a plain browser there is no local filesystem access, so auto-provision
 * is disabled and the manual token flow is used instead.
 * @returns Desktop detection + the provisioning action.
 */
export function useMachineProvision() {
  const { isDesktopApp } = useDesktopRuntime()
  const config = useRuntimeConfig()

  /**
   * Best-effort machine name from the OS hostname, falling back to a generic label.
   * @returns The detected machine name.
   */
  async function detectMachineName(): Promise<string> {
    try {
      const os = await import('@tauri-apps/plugin-os')
      const name = await os.hostname()
      if (name && name.trim()) {
        return name.trim()
      }
    } catch {
      // Plugin unavailable (not desktop) — fall through to the default.
    }
    return 'Cette machine'
  }

  /**
   * Read the shared provisioning file if present.
   * @returns Parsed provisioning payload or null.
   */
  async function readProvisionFile(): Promise<{
    agent_token?: string
    machine_id?: number
    api_base?: string
    machine_name?: string
  } | null> {
    if (!isDesktopApp.value) {
      return null
    }
    try {
      const fs = await import('@tauri-apps/plugin-fs')
      const text = await fs.readTextFile(PROVISION_FILE, { baseDir: fs.BaseDirectory.Home })
      const data = JSON.parse(text) as unknown
      return data && typeof data === 'object' ? (data as Record<string, unknown>) : null
    } catch {
      return null
    }
  }

  /**
   * Write the shared provisioning file so the local agent can authenticate.
   * @param machine - The freshly created machine (with its one-time token).
   * @returns Nothing.
   */
  async function writeProvisionFile(machine: MachineCreated): Promise<void> {
    const fs = await import('@tauri-apps/plugin-fs')
    const payload = JSON.stringify(
      {
        api_base: config.public.apiBase,
        agent_token: machine.agent_token,
        machine_id: machine.id,
        machine_name: machine.name,
      },
      null,
      2,
    )
    await fs.mkdir(PROVISION_DIR, { baseDir: fs.BaseDirectory.Home, recursive: true })
    await fs.writeTextFile(PROVISION_FILE, payload, { baseDir: fs.BaseDirectory.Home })
  }

  /**
   * Restart the bundled agent sidecar so it reloads `~/.nightforge/agent.json`.
   * @returns Nothing.
   */
  async function restartLocalAgent(): Promise<void> {
    if (!isDesktopApp.value) {
      return
    }
    const { invoke } = await import('@tauri-apps/api/core')
    await invoke('restart_agent')
  }

  /**
   * Register the current machine and configure the local agent in one step.
   * Reuses an existing machine with the same hostname and rotates its token when needed.
   * @returns The created or refreshed machine.
   */
  async function provisionThisMachine(): Promise<MachineCreated> {
    const name = await detectMachineName()
    const machines = await listMachines().catch(() => [])
    const provisioned = await readProvisionFile()

    let existing = machines.find((machine) => machine.name.toLowerCase() === name.toLowerCase())
    if (!existing && provisioned?.machine_id) {
      existing = machines.find((machine) => machine.id === provisioned.machine_id)
    }

    const machine = existing ? await reissueMachineToken(existing.id) : await createMachine(name)

    await writeProvisionFile(machine)
    await restartLocalAgent()
    return machine
  }

  /**
   * If this PC already has a provisioning file, restart the agent so it reconnects.
   * @returns True when a restart was attempted.
   */
  async function syncLocalAgentIfProvisioned(): Promise<boolean> {
    if (!isDesktopApp.value) {
      return false
    }
    const provisioned = await readProvisionFile()
    if (!provisioned?.agent_token?.trim()) {
      return false
    }
    await restartLocalAgent()
    return true
  }

  /**
   * Query the Tauri sidecar status (desktop only).
   * @returns Sidecar running flag and last spawn error.
   */
  async function getAgentStatus(): Promise<{ sidecarRunning: boolean; lastError: string | null }> {
    if (!isDesktopApp.value) {
      return { sidecarRunning: false, lastError: null }
    }
    const { invoke } = await import('@tauri-apps/api/core')
    return invoke('agent_status')
  }

  /**
   * Read the last lines of ~/.nightforge/agent.log (desktop only).
   * @param lines - Number of lines to return.
   * @returns Log tail text.
   */
  async function getAgentLogTail(lines = 15): Promise<string> {
    if (!isDesktopApp.value) {
      return ''
    }
    const { invoke } = await import('@tauri-apps/api/core')
    return invoke<string>('agent_log_tail', { lines })
  }

  return {
    isDesktopApp,
    provisionThisMachine,
    detectMachineName,
    restartLocalAgent,
    writeProvisionFile,
    readProvisionFile,
    syncLocalAgentIfProvisioned,
    getAgentStatus,
    getAgentLogTail,
  }
}
