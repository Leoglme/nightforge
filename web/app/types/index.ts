/**
 * Shared front-end types for NightForge.
 * @module types
 */

export type UserRole = 'USER' | 'ADMIN'

export interface User {
  id: number
  name: string
  email: string
  role: UserRole
  is_active: boolean
  created_at: string
  updated_at?: string | null
}

export interface LoginCredentials {
  email: string
  password: string
}

export interface TokenResponse {
  access_token: string
  token_type: string
}

export type MachineStatus = 'OFFLINE' | 'IDLE' | 'WORKING' | 'WAITING_QUOTA' | 'ERROR'

export interface Machine {
  id: number
  name: string
  status: MachineStatus
  online: boolean
  last_seen_at?: string | null
  claude_version?: string | null
  agent_version?: string | null
  created_at: string
}

export interface MachineCreated extends Machine {
  agent_token: string
}

export interface Project {
  id: number
  name: string
  github_repo: string
  base_branch: string
  created_at: string
  pending_count: number
}

export type QueueItemStatus = 'PENDING' | 'RUNNING' | 'DONE' | 'FAILED' | 'SKIPPED'

export interface QueueItem {
  id: number
  project_id: number
  prompt: string
  priority: number
  status: QueueItemStatus
  created_from?: string | null
  error?: string | null
  created_at: string
}

export type RunStatus = 'SCHEDULED' | 'RUNNING' | 'WAITING_QUOTA' | 'COMPLETED' | 'STOPPED' | 'FAILED'

export interface QuotaWindow {
  index: number
  starts_at: string
  resets_at: string
  estimated: boolean
}

export interface QuotaPlan {
  windows: QuotaWindow[]
  fresh_quota_available_at: string
  hours_after_wake?: number | null
  weekly_warning?: string | null
}

export interface Run {
  id: number
  machine_id: number
  status: RunStatus
  quota_count: number
  parallel: boolean
  planned_timeline?: QuotaPlan | null
  scheduled_at?: string | null
  started_at?: string | null
  window_end?: string | null
  finished_at?: string | null
  created_at: string
}

export interface RunEvent {
  id: number
  level: string
  message: string
  queue_item_id?: number | null
  created_at: string
}

export interface ProjectPath {
  id: number
  project_id: number
  machine_id: number
  local_path: string
}

export interface ClaudeSession {
  session_id: string
  title?: string | null
  cwd?: string | null
  updated_at: string
}

export interface ProjectMessage {
  id: number
  project_id: number
  order_index: number
  content: string
  claude_session_id?: string | null
  claude_model?: string | null
  source_item_ids?: number[] | null
  created_from?: string | null
  created_at: string
}

export interface RunMessage {
  id: number
  run_id: number
  project_id: number
  order_index: number
  content: string
  claude_session_id?: string | null
  claude_model?: string | null
  status: QueueItemStatus
  error?: string | null
  created_at: string
}
