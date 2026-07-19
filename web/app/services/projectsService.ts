import type { Project, ProjectPath } from '~/types'
import { api } from '~/services/api'

/**
 * Projects API service.
 * @module services/projectsService
 */

/**
 * List the current user's projects.
 * @returns The projects.
 */
export function listProjects(): Promise<Project[]> {
  return api.get<Project[]>('/api/v1/projects')
}

/**
 * Create a project.
 * @param payload - Project fields.
 * @returns The created project.
 */
export function createProject(payload: {
  name: string
  github_repo?: string
  base_branch?: string
  push_to_main?: boolean
  allow_push?: boolean
}): Promise<Project> {
  return api.post<Project>('/api/v1/projects', payload)
}

/**
 * Update a project.
 * @param id - Project id.
 * @param payload - Fields to update.
 * @returns The updated project.
 */
export function updateProject(id: number, payload: Partial<Project>): Promise<Project> {
  return api.patch<Project>(`/api/v1/projects/${id}`, payload)
}

/**
 * Delete a project.
 * @param id - Project id.
 * @returns Nothing.
 */
export function deleteProject(id: number): Promise<void> {
  return api.delete(`/api/v1/projects/${id}`)
}

/**
 * List a project's local clone paths across machines.
 * @param id - Project id.
 * @returns The machine paths.
 */
export function listProjectPaths(id: number): Promise<ProjectPath[]> {
  return api.get<ProjectPath[]>(`/api/v1/projects/${id}/paths`)
}

/**
 * Set (or update) a project's local clone path on a machine.
 * @param id - Project id.
 * @param payload - Machine id and local path.
 * @returns The upserted path.
 */
export function setProjectPath(id: number, payload: { machine_id: number; local_path: string }): Promise<ProjectPath> {
  return api.put<ProjectPath>(`/api/v1/projects/${id}/paths`, payload)
}
