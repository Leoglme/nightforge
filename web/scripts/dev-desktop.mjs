/*
 * Dev orchestrator for the NightForge desktop app.
 *
 * Tauri's `beforeDevCommand` runs this so a single `npm run tauri:dev` boots BOTH the web
 * app (port 1420) and the local Python agent — nothing else to start by hand. In packaged
 * builds the agent is launched as a Tauri sidecar instead (see src-tauri/src/lib.rs).
 *
 * We use concurrently's programmatic API instead of an inline shell string because, on
 * Windows, cmd.exe mangles the nested quotes of `concurrently "cmd a" "cmd b"`.
 */
import { spawnSync } from 'node:child_process'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import concurrently from 'concurrently'

const __dirname = dirname(fileURLToPath(import.meta.url))

// Tauri refuses to compile without the externalBin file — create a stub if needed.
const ensure = spawnSync(process.execPath, [join(__dirname, 'ensure-agent-sidecar.mjs')], {
  stdio: 'inherit',
})
if (ensure.status !== 0) {
  process.exit(ensure.status ?? 1)
}

const { result } = concurrently(
  [
    {
      command: 'cross-env NUXT_DESKTOP_BUILD=1 nuxt dev --port 1420',
      name: 'web',
      prefixColor: 'cyan',
    },
    {
      command: 'python -m nightforge_agent',
      name: 'agent',
      cwd: '../agent',
      prefixColor: 'magenta',
    },
  ],
  {
    prefix: 'name',
    restartTries: 0,
  },
)

// The agent is best-effort in dev (it needs NF_AGENT_TOKEN): if it fails, the web app must
// still launch, so swallow the rejection rather than crash the whole dev command.
result.catch(() => {})
