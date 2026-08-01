import type { Machine, MachineCreated } from '~/types'
import { api } from '~/services/api'

/**
 * Machines API service.
 * @module services/machinesService
 */

/**
 * List the current user's machines.
 * @returns The machines.
 */
export function listMachines(): Promise<Machine[]> {
  return api.get<Machine[]>('/api/v1/machines')
}

/**
 * Register a new machine (returns a one-time agent token).
 * @param name - Machine display name.
 * @returns The created machine with its agent token.
 */
export function createMachine(name: string): Promise<MachineCreated> {
  return api.post<MachineCreated>('/api/v1/machines', { name })
}

/**
 * Rotate the agent token for an existing machine (desktop re-provisioning).
 * @param id - Machine id.
 * @returns The machine with a fresh agent token.
 */
export function reissueMachineToken(id: number): Promise<MachineCreated> {
  return api.post<MachineCreated>(`/api/v1/machines/${id}/reissue-token`)
}

/**
 * Delete a machine.
 * @param id - Machine id.
 * @returns Nothing.
 */
export function deleteMachine(id: number): Promise<void> {
  return api.delete(`/api/v1/machines/${id}`)
}

/**
 * List resumable Claude Code sessions on a machine.
 * @param machineId - Machine id.
 * @param localPath - Optional project clone path; omit to list every session on the machine.
 * @returns Recent sessions, each mapped to a project when known.
 */
export function listClaudeSessions(
  machineId: number,
  localPath?: string,
): Promise<{ sessions: import('~/types').ClaudeSession[] }> {
  const query = localPath ? `?local_path=${encodeURIComponent(localPath)}` : ''
  return api.get(`/api/v1/machines/${machineId}/claude-sessions${query}`)
}

/**
 * Inspect a local git clone on a machine (folder name + GitHub remote).
 * @param machineId - Machine id (must be online).
 * @param localPath - Absolute path on that PC.
 * @returns Detected metadata.
 */
export function inspectRepo(machineId: number, localPath: string): Promise<import('~/types').RepoInspect> {
  const query = encodeURIComponent(localPath)
  return api.get(`/api/v1/machines/${machineId}/inspect-repo?local_path=${query}`)
}
