/**
 * Shared front-end types for NightForge.
 * @module types
 */

export type UserRole = 'USER' | 'ADMIN'

export type User = {
  id: number
  name: string
  email: string
  role: UserRole
  is_active: boolean
  created_at: string
  updated_at?: string | null
}

export type LoginCredentials = {
  email: string
  password: string
}

export type SignupCredentials = {
  name: string
  email: string
  password: string
}

export type TokenResponse = {
  access_token: string
  token_type: string
}

export type MachineStatus = 'OFFLINE' | 'IDLE' | 'WORKING' | 'WAITING_QUOTA' | 'ERROR'

export type Machine = {
  id: number
  name: string
  status: MachineStatus
  online: boolean
  last_seen_at?: string | null
  claude_version?: string | null
  cursor_version?: string | null
  agent_version?: string | null
  created_at: string
}

export interface MachineCreated extends Machine {
  agent_token: string
}

export type Project = {
  id: number
  name: string
  github_repo: string
  base_branch: string
  push_to_main?: boolean
  allow_push?: boolean
  created_at: string
  pending_count: number
}

export type RepoInspect = {
  exists: boolean
  is_git: boolean
  name?: string | null
  github_repo?: string | null
  base_branch?: string | null
  error?: string | null
}

export type QueueItemStatus = 'PENDING' | 'RUNNING' | 'DONE' | 'FAILED' | 'SKIPPED'

export type AiProvider = 'claude' | 'cursor'

export type QueueItem = {
  id: number
  project_id: number
  prompt: string
  title?: string | null
  provider?: AiProvider | string | null
  model?: string | null
  effort?: string | null
  fast_mode?: boolean
  priority: number
  status: QueueItemStatus
  created_from?: string | null
  error?: string | null
  created_at: string
}

export type RunStatus = 'SCHEDULED' | 'RUNNING' | 'WAITING_QUOTA' | 'COMPLETED' | 'STOPPED' | 'FAILED'

export type RunKind = 'night' | 'quick'

export type QuotaWindow = {
  index: number
  starts_at: string
  resets_at: string
  estimated: boolean
}

export type QuotaPlan = {
  windows: QuotaWindow[]
  fresh_quota_available_at: string
  wait_until?: string | null
  anchor_source?: 'live' | 'snapshot' | 'none' | null
  hours_after_wake?: number | null
  weekly_warning?: string | null
  quota_auth_error?: string | null
}

export type UsageBucket = {
  bucket: string
  label: string
  utilization: number
  remaining: number
  resets_at?: string | null
  created_at?: string | null
}

export type UsageSummary = {
  claude: UsageBucket[]
  cursor?: UsageBucket[] | null
  source?: string | null
  quota_auth_error?: string | null
}

export type CursorAccount = {
  id: number
  label: string
  email?: string | null
  has_password: boolean
  has_session_token: boolean
  has_api_key: boolean
  auto_utilization?: number | null
  api_utilization?: number | null
  average_utilization?: number | null
  resets_at?: string | null
  last_checked_at?: string | null
  last_error?: string | null
  is_active: boolean
  created_at: string
  updated_at?: string | null
}

export type CursorAccountCredentials = {
  id: number
  label: string
  email?: string | null
  password?: string | null
}

export type MachineCursorUsage = {
  pinned: boolean
  label: string
  email?: string | null
  auto_utilization?: number | null
  api_utilization?: number | null
  average_utilization?: number | null
  resets_at?: string | null
  source: string
  error?: string | null
  buckets: Array<{
    bucket?: string
    label?: string
    utilization?: number | null
    resets_at?: string | null
  }>
}

export type CursorAccountsOverview = {
  machine?: MachineCursorUsage | null
  accounts: CursorAccount[]
  selected_account_id?: number | null
  machine_imported?: boolean
  machine_preferred?: boolean
}

export type CursorAccountCreatePayload = {
  email: string
  password?: string | null
  session_token?: string | null
  api_key?: string | null
  /** @deprecated Kept for API compat — derived from email server-side. */
  label?: string
}

export type CursorAccountUpdatePayload = {
  email?: string | null
  password?: string | null
  session_token?: string | null
  api_key?: string | null
  is_active?: boolean
  clear_password?: boolean
  clear_session_token?: boolean
  clear_api_key?: boolean
  /** @deprecated Kept for API compat — synced from email when provided. */
  label?: string
}

export type ClaudeAccount = {
  id: number
  label: string
  email?: string | null
  has_password: boolean
  has_oauth: boolean
  five_hour_utilization?: number | null
  seven_day_utilization?: number | null
  seven_day_opus_utilization?: number | null
  resets_at?: string | null
  last_checked_at?: string | null
  last_error?: string | null
  is_active: boolean
  created_at: string
  updated_at?: string | null
}

export type ClaudeAccountCredentials = {
  id: number
  label: string
  email?: string | null
  password?: string | null
}

export type MachineClaudeUsage = {
  pinned: boolean
  label: string
  email?: string | null
  five_hour_utilization?: number | null
  seven_day_utilization?: number | null
  seven_day_opus_utilization?: number | null
  resets_at?: string | null
  source: string
  error?: string | null
  buckets: Array<{
    bucket?: string
    label?: string
    utilization?: number | null
    resets_at?: string | null
  }>
}

export type ClaudeAccountsOverview = {
  machine?: MachineClaudeUsage | null
  accounts: ClaudeAccount[]
  selected_account_id?: number | null
  machine_imported?: boolean
  machine_preferred?: boolean
}

export type ClaudeAccountCreatePayload = {
  email?: string | null
  password?: string | null
  oauth?: Record<string, unknown> | null
  oauth_json?: string | null
  access_token?: string | null
  label?: string
}

export type ClaudeAccountUpdatePayload = {
  email?: string | null
  password?: string | null
  oauth?: Record<string, unknown> | null
  oauth_json?: string | null
  access_token?: string | null
  is_active?: boolean
  clear_password?: boolean
  clear_oauth?: boolean
  /** @deprecated Kept for API compat — synced from email when provided. */
  label?: string
}

export type Run = {
  id: number
  machine_id: number
  status: RunStatus
  kind?: RunKind | string
  quota_count: number
  parallel: boolean
  planned_timeline?: QuotaPlan | null
  scheduled_at?: string | null
  started_at?: string | null
  window_end?: string | null
  finished_at?: string | null
  created_at: string
  /** Conversation-hub enrichments (populated by the list endpoint). */
  project_names?: string[]
  title?: string | null
  last_activity_at?: string | null
}

export type RunEvent = {
  id: number
  level: string
  message: string
  queue_item_id?: number | null
  created_at: string
}

export type ProjectPath = {
  id: number
  project_id: number
  machine_id: number
  local_path: string
}

export type ClaudeSession = {
  session_id: string
  title?: string | null
  cwd?: string | null
  updated_at: string
  /** Registered project this session's cwd maps to, when known. */
  project_id?: number | null
  project_name?: string | null
  /** True while NightForge is running a message that resumes this session. */
  is_running?: boolean
}

export type SessionTranscriptEvent = {
  level: string
  message: string
}

export type SessionTranscriptTurn = {
  role: string
  content: string
  events: SessionTranscriptEvent[]
}

export type SessionTranscript = {
  session_id: string
  cwd?: string | null
  project_id?: number | null
  project_name?: string | null
  turns: SessionTranscriptTurn[]
}

export type ProjectMessage = {
  id: number
  project_id: number
  order_index: number
  content: string
  claude_session_id?: string | null
  claude_model?: string | null
  provider?: AiProvider | string | null
  effort?: string | null
  fast_mode?: boolean
  source_item_ids?: number[] | null
  created_from?: string | null
  created_at: string
}

export type RunMessage = {
  id: number
  run_id: number
  project_id: number
  order_index: number
  content: string
  claude_session_id?: string | null
  claude_model?: string | null
  provider?: AiProvider | string | null
  effort?: string | null
  fast_mode?: boolean
  status: QueueItemStatus
  error?: string | null
  created_at: string
}
