import type {
  CursorAccount,
  CursorAccountCredentials,
  CursorAccountsOverview,
  CursorAccountCreatePayload,
  CursorAccountUpdatePayload,
} from '~/types'
import { api } from '~/services/api'

/**
 * Cursor multi-account vault API.
 * @module services/cursorAccountsService
 */

/**
 * List vault accounts + pinned machine usage.
 */
export function listCursorAccounts(): Promise<CursorAccountsOverview> {
  return api.get<CursorAccountsOverview>('/api/v1/cursor-accounts')
}

/**
 * Refresh usage for every vault account and the machine session.
 */
export function refreshCursorAccounts(): Promise<CursorAccountsOverview> {
  return api.post<CursorAccountsOverview>('/api/v1/cursor-accounts/refresh')
}

/**
 * Create a vaulted Cursor account.
 */
export function createCursorAccount(payload: CursorAccountCreatePayload): Promise<CursorAccount> {
  return api.post<CursorAccount>('/api/v1/cursor-accounts', payload)
}

/**
 * Update a vaulted Cursor account.
 */
export function updateCursorAccount(id: number, payload: CursorAccountUpdatePayload): Promise<CursorAccount> {
  return api.patch<CursorAccount>(`/api/v1/cursor-accounts/${id}`, payload)
}

/**
 * Delete a vaulted Cursor account.
 */
export function deleteCursorAccount(id: number): Promise<void> {
  return api.delete(`/api/v1/cursor-accounts/${id}`)
}

/**
 * Reveal decrypted email/password reminder for the credentials drawer.
 */
export function fetchCursorCredentials(id: number): Promise<CursorAccountCredentials> {
  return api.get<CursorAccountCredentials>(`/api/v1/cursor-accounts/${id}/credentials`)
}

/**
 * Import the local Cursor IDE session from an online agent into the vault.
 */
export function importMachineCursorSession(): Promise<CursorAccount> {
  return api.post<CursorAccount>('/api/v1/cursor-accounts/import-machine')
}

export interface CursorLoginStart {
  login_id: string
  login_url?: string | null
  status: string
  mode?: 'browser' | 'ide' | 'cli' | string | null
  note?: string | null
  warning?: string | null
  machine_id?: number
  session_token?: string | null
  email?: string | null
}

export interface CursorLoginResult {
  status: string
  session_token?: string | null
  email?: string | null
  error?: string | null
  note?: string | null
  restored_machine_session?: boolean
  login_url?: string | null
  elapsed_seconds?: number
  browser_ready?: boolean
}

/**
 * Start Cursor NoDriver login on the agent (opens isolated Chromium).
 */
export function startCursorLogin(): Promise<CursorLoginStart> {
  return api.post<CursorLoginStart>('/api/v1/cursor-accounts/login/start')
}

/**
 * Poll login progress.
 */
export function pollCursorLogin(loginId: string): Promise<CursorLoginResult> {
  return api.post<CursorLoginResult>('/api/v1/cursor-accounts/login/poll', { login_id: loginId })
}

/**
 * Confirm login finished and capture the session token.
 */
export function completeCursorLogin(loginId: string): Promise<CursorLoginResult> {
  return api.post<CursorLoginResult>('/api/v1/cursor-accounts/login/complete', { login_id: loginId })
}

/**
 * Cancel login and restore the previous machine Cursor session.
 */
export function cancelCursorLogin(loginId: string): Promise<{ status: string }> {
  return api.post('/api/v1/cursor-accounts/login/cancel', { login_id: loginId })
}
