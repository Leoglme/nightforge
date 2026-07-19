import type {
  ClaudeAccount,
  ClaudeAccountCredentials,
  ClaudeAccountsOverview,
  ClaudeAccountCreatePayload,
  ClaudeAccountUpdatePayload,
} from '~/types'
import { api } from '~/services/api'

/**
 * Claude multi-account vault API.
 * @module services/claudeAccountsService
 */

/**
 * List vault accounts + pinned machine usage.
 */
export function listClaudeAccounts(): Promise<ClaudeAccountsOverview> {
  return api.get<ClaudeAccountsOverview>('/api/v1/claude-accounts')
}

/**
 * Refresh usage for every vault account and the machine session.
 */
export function refreshClaudeAccounts(): Promise<ClaudeAccountsOverview> {
  return api.post<ClaudeAccountsOverview>('/api/v1/claude-accounts/refresh')
}

/**
 * Create a vaulted Claude account.
 */
export function createClaudeAccount(payload: ClaudeAccountCreatePayload): Promise<ClaudeAccount> {
  return api.post<ClaudeAccount>('/api/v1/claude-accounts', payload)
}

/**
 * Update a vaulted Claude account.
 */
export function updateClaudeAccount(id: number, payload: ClaudeAccountUpdatePayload): Promise<ClaudeAccount> {
  return api.patch<ClaudeAccount>(`/api/v1/claude-accounts/${id}`, payload)
}

/**
 * Delete a vaulted Claude account.
 */
export function deleteClaudeAccount(id: number): Promise<void> {
  return api.delete(`/api/v1/claude-accounts/${id}`)
}

/**
 * Reveal decrypted email/password reminder for the credentials drawer.
 */
export function fetchClaudeCredentials(id: number): Promise<ClaudeAccountCredentials> {
  return api.get<ClaudeAccountCredentials>(`/api/v1/claude-accounts/${id}/credentials`)
}

/**
 * Import the local Claude session from an online agent into the vault.
 */
export function importMachineClaudeSession(): Promise<ClaudeAccount> {
  return api.post<ClaudeAccount>('/api/v1/claude-accounts/import-machine')
}

export interface ClaudeLoginStart {
  login_id: string
  login_url?: string | null
  status: string
  mode?: 'cli' | 'browser' | string | null
  note?: string | null
  warning?: string | null
  keep_on_machine?: boolean
  machine_id?: number
}

export interface ClaudeLoginResult {
  status: string
  oauth?: Record<string, unknown> | null
  email?: string | null
  error?: string | null
  note?: string | null
  login_url?: string | null
  elapsed_seconds?: number
}

/**
 * Start Claude account capture on the agent (``claude auth login``).
 *
 * @param options.keepOnMachine - Leave the new session on the machine (first connect / re-import).
 */
export function startClaudeLogin(options?: { keepOnMachine?: boolean }): Promise<ClaudeLoginStart> {
  return api.post<ClaudeLoginStart>('/api/v1/claude-accounts/login/start', {
    keep_on_machine: Boolean(options?.keepOnMachine),
  })
}

/**
 * Poll login progress.
 */
export function pollClaudeLogin(loginId: string): Promise<ClaudeLoginResult> {
  return api.post<ClaudeLoginResult>('/api/v1/claude-accounts/login/poll', { login_id: loginId })
}

/**
 * Confirm login finished and capture the OAuth block.
 */
export function completeClaudeLogin(loginId: string): Promise<ClaudeLoginResult> {
  return api.post<ClaudeLoginResult>('/api/v1/claude-accounts/login/complete', { login_id: loginId })
}

/**
 * Cancel login and restore the previous machine Claude session.
 */
export function cancelClaudeLogin(loginId: string): Promise<{ status: string }> {
  return api.post('/api/v1/claude-accounts/login/cancel', { login_id: loginId })
}
