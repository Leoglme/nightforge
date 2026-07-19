import type { AiProvider, QueueItem } from '~/types'
import { api } from '~/services/api'

/**
 * Queue API service (prompts of a project).
 * @module services/queueService
 */

export interface QueueItemPayload {
  prompt: string
  title?: string | null
  provider?: AiProvider | string | null
  model?: string | null
  effort?: string | null
  fast_mode?: boolean
  priority?: number
  created_from?: string
}

export interface IdeasExpandPayload {
  ideas: string
  machine_id?: number | null
  prefer_provider?: 'cursor' | 'claude'
}

export interface IdeasExpandResult {
  summary?: string | null
  source: 'agent' | 'groq' | 'heuristic'
  provider_used?: string | null
  model_used?: string | null
  items: QueueItem[]
}

/**
 * List a project's queue.
 * @param projectId - Project id.
 * @param includeDone - Include prompts already completed.
 * @returns The ordered queue items.
 */
export function listQueue(projectId: number, includeDone = false): Promise<QueueItem[]> {
  const query = includeDone ? '?include_done=true' : ''
  return api.get<QueueItem[]>(`/api/v1/projects/${projectId}/queue${query}`)
}

/**
 * Add a prompt to a project's queue.
 * @param projectId - Project id.
 * @param payload - Prompt payload.
 * @returns The created queue item.
 */
export function addQueueItem(projectId: number, payload: QueueItemPayload): Promise<QueueItem> {
  return api.post<QueueItem>(`/api/v1/projects/${projectId}/queue`, payload)
}

/**
 * Expand free-form ideas into queue prompts (agent or heuristic).
 * @param projectId - Project id.
 * @param payload - Ideas + optional machine.
 * @returns Created items + expansion metadata.
 */
export function expandIdeas(projectId: number, payload: IdeasExpandPayload): Promise<IdeasExpandResult> {
  return api.post<IdeasExpandResult>(`/api/v1/projects/${projectId}/queue/expand`, payload)
}

/**
 * Update a queue item (prompt + metadata).
 * @param projectId - Project id.
 * @param itemId - Queue item id.
 * @param payload - Fields to update.
 * @returns The updated item.
 */
export function updateQueueItem(
  projectId: number,
  itemId: number,
  payload: Partial<QueueItemPayload>,
): Promise<QueueItem> {
  return api.patch<QueueItem>(`/api/v1/projects/${projectId}/queue/${itemId}`, payload)
}

/**
 * Delete a queue item.
 * @param projectId - Project id.
 * @param itemId - Queue item id.
 * @returns Nothing.
 */
export function deleteQueueItem(projectId: number, itemId: number): Promise<void> {
  return api.delete(`/api/v1/projects/${projectId}/queue/${itemId}`)
}
