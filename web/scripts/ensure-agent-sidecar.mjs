/*
 * Ensure a stub NightForge agent sidecar exists for `tauri:dev`.
 *
 * Tauri requires `externalBin` files to exist at compile time (with -$TARGET_TRIPLE
 * suffix). In development the real agent is started as Python by `dev-desktop.mjs`,
 * so a zero-byte placeholder is enough for Cargo / Tauri to proceed. Packaged
 * builds must replace this with a real PyInstaller binary.
 */
import { existsSync, mkdirSync, writeFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'
import { execSync } from 'node:child_process'

const __dirname = dirname(fileURLToPath(import.meta.url))
const binariesDir = join(__dirname, '..', 'src-tauri', 'binaries')

/**
 * Resolve the Rust host target triple (e.g. x86_64-pc-windows-msvc).
 * @returns {string}
 */
function hostTriple() {
  const fromEnv = process.env.TAURI_ENV_TARGET_TRIPLE || process.env.CARGO_BUILD_TARGET
  if (fromEnv) {
    return fromEnv.trim()
  }
  try {
    return execSync('rustc -vV', { encoding: 'utf8' })
      .split('\n')
      .find((line) => line.startsWith('host:'))
      ?.slice(5)
      .trim()
  } catch {
    return null
  }
}

const triple = hostTriple()
if (!triple) {
  console.error('[ensure-agent-sidecar] Could not detect Rust host triple (is rustc installed?)')
  process.exit(1)
}

mkdirSync(binariesDir, { recursive: true })

const base = join(binariesDir, `nightforge-agent-${triple}`)
const candidates = process.platform === 'win32' ? [`${base}.exe`, base] : [base]

const missing = candidates.filter((path) => !existsSync(path))
if (missing.length === 0) {
  console.log(`[ensure-agent-sidecar] OK — sidecar present for ${triple}`)
  process.exit(0)
}

// Create stubs for any missing variant Tauri might look for.
for (const path of missing) {
  writeFileSync(path, '')
  console.log(`[ensure-agent-sidecar] Created stub: ${path}`)
}
console.log(
  '[ensure-agent-sidecar] Stub only — real agent in tauri:dev is `python -m nightforge_agent` via concurrently.',
)
