import type { QueueItem } from '~/types'
import { api } from '~/services/api'

/**
 * Queue API service (prompts of a project).
 * @module services/queueService
 */

/**
 * List a project's queue.
 * @param projectId - Project id.
 * @returns The ordered queue items.
 */
export function listQueue(projectId: number): Promise<QueueItem[]> {
  return api.get<QueueItem[]>(`/api/v1/projects/${projectId}/queue`)
}

/**
 * Add a prompt to a project's queue.
 * @param projectId - Project id.
 * @param payload - Prompt payload.
 * @returns The created queue item.
 */
export function addQueueItem(
  projectId: number,
  payload: { prompt: string; priority?: number; created_from?: string },
): Promise<QueueItem> {
  return api.post<QueueItem>(`/api/v1/projects/${projectId}/queue`, payload)
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
