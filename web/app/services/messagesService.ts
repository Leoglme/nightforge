import type { ProjectMessage } from '~/types'
import { api } from '~/services/api'

/**
 * Project night-message drafts API service (the chat composer store).
 * @module services/messagesService
 */

/**
 * List a project's night-message drafts in order.
 * @param projectId - Project id.
 * @returns The ordered message drafts.
 */
export function listMessages(projectId: number): Promise<ProjectMessage[]> {
  return api.get<ProjectMessage[]>(`/api/v1/projects/${projectId}/messages`)
}

/**
 * Append a night-message draft to a project's sequence.
 * @param projectId - Project id.
 * @param payload - Message content and optional source queue item ids.
 * @returns The created message draft.
 */
export function createMessage(
  projectId: number,
  payload: {
    content: string
    claude_session_id?: string | null
    claude_model?: string | null
    provider?: string | null
    effort?: string | null
    fast_mode?: boolean
    source_item_ids?: number[]
    created_from?: string
  },
): Promise<ProjectMessage> {
  return api.post<ProjectMessage>(`/api/v1/projects/${projectId}/messages`, payload)
}

/**
 * Edit a night-message draft.
 * @param projectId - Project id.
 * @param messageId - Message id.
 * @param payload - Fields to update.
 * @returns The updated message draft.
 */
export function updateMessage(
  projectId: number,
  messageId: number,
  payload: {
    content?: string
    claude_session_id?: string | null
    claude_model?: string | null
    provider?: string | null
    effort?: string | null
    fast_mode?: boolean
    source_item_ids?: number[]
  },
): Promise<ProjectMessage> {
  return api.patch<ProjectMessage>(`/api/v1/projects/${projectId}/messages/${messageId}`, payload)
}

/**
 * Reorder a project's night-message drafts.
 * @param projectId - Project id.
 * @param orderedIds - Message ids in the desired order.
 * @returns The reordered message drafts.
 */
export function reorderMessages(projectId: number, orderedIds: number[]): Promise<ProjectMessage[]> {
  return api.post<ProjectMessage[]>(`/api/v1/projects/${projectId}/messages/reorder`, {
    ordered_ids: orderedIds,
  })
}

/**
 * Delete a night-message draft.
 * @param projectId - Project id.
 * @param messageId - Message id.
 * @returns Nothing.
 */
export function deleteMessage(projectId: number, messageId: number): Promise<void> {
  return api.delete(`/api/v1/projects/${projectId}/messages/${messageId}`)
}
