import type { Run, RunEvent, RunMessage } from '~/types'
import { api } from '~/services/api'

/**
 * Runs API service.
 * @module services/runsService
 */

/**
 * List the current user's runs.
 * @returns The runs (most recent first).
 */
export function listRuns(): Promise<Run[]> {
  return api.get<Run[]>('/api/v1/runs')
}

/**
 * Schedule a night run.
 * @param payload - Run creation payload.
 * @returns The scheduled run.
 */
export function createRun(payload: {
  machine_id: number
  project_ids: number[]
  quota_count: number
  parallel: boolean
  scheduled_at?: string | null
  window_end?: string | null
  wait_for_fresh_quota?: boolean
}): Promise<Run> {
  return api.post<Run>('/api/v1/runs', payload)
}

/**
 * Get a single run.
 * @param id - Run id.
 * @returns The run.
 */
export function getRun(id: number): Promise<Run> {
  return api.get<Run>(`/api/v1/runs/${id}`)
}

/**
 * Stop a run (kill switch).
 * @param id - Run id.
 * @returns The updated run.
 */
export function stopRun(id: number): Promise<Run> {
  return api.post<Run>(`/api/v1/runs/${id}/stop`)
}

/**
 * List the events/log of a run, optionally only those newer than a given id.
 * @param id - Run id.
 * @param afterId - Only return events with an id strictly greater than this.
 * @returns The run's events.
 */
export function listRunEvents(id: number, afterId = 0): Promise<RunEvent[]> {
  return api.get<RunEvent[]>(`/api/v1/runs/${id}/events?after_id=${afterId}`)
}

/**
 * List a run's frozen night-message sequence and its progress.
 * @param id - Run id.
 * @returns The run's messages.
 */
export function listRunMessages(id: number): Promise<RunMessage[]> {
  return api.get<RunMessage[]>(`/api/v1/runs/${id}/messages`)
}

const CONTINUE_PROMPT = "Vas-y, continue là où tu t'étais arrêté."

/**
 * Re-queue a run message (optionally resuming a Claude session).
 * @param runId - Run id.
 * @param messageId - Message id.
 * @param payload - Optional overrides.
 * @returns The updated message.
 */
export function retryRunMessage(
  runId: number,
  messageId: number,
  payload?: { content?: string; claude_session_id?: string | null; claude_model?: string | null },
): Promise<RunMessage> {
  return api.post<RunMessage>(`/api/v1/runs/${runId}/messages/${messageId}/retry`, payload ?? {})
}

/**
 * Retry with the default continue prompt (uses stored session id when present).
 * @param runId - Run id.
 * @param message - The message to retry.
 * @returns The updated message.
 */
export function continueRunMessage(runId: number, message: RunMessage): Promise<RunMessage> {
  return retryRunMessage(runId, message.id, {
    content: CONTINUE_PROMPT,
    claude_session_id: message.claude_session_id ?? undefined,
  })
}

/**
 * Add extra quota windows to an active run without stopping it.
 * @param runId - Run id.
 * @param add - Number of quotas to add.
 * @returns The updated run.
 */
export function addRunQuotas(runId: number, add: number): Promise<Run> {
  return api.post<Run>(`/api/v1/runs/${runId}/quotas`, { add })
}

export interface RunProjectSummary {
  project_id: number
  name: string
  order_index: number
  local_path?: string | null
}

/**
 * List projects attached to a run.
 * @param runId - Run id.
 * @returns Projects in execution order.
 */
export function listRunProjects(runId: number): Promise<RunProjectSummary[]> {
  return api.get<RunProjectSummary[]>(`/api/v1/runs/${runId}/projects`)
}

/**
 * Append a message to an active run's sequence.
 * @param runId - Run id.
 * @param payload - Message content and target project.
 * @returns The created message.
 */
export function addRunMessage(
  runId: number,
  payload: {
    project_id: number
    content: string
    claude_session_id?: string | null
    claude_model?: string | null
  },
): Promise<RunMessage> {
  return api.post<RunMessage>(`/api/v1/runs/${runId}/messages`, payload)
}
