import type { QuotaPlan } from '~/types'
import { api } from '~/services/api'

/**
 * Quota planner API service.
 * @module services/quotaService
 */

/**
 * Compute the quota timeline for N sequential 5-hour windows.
 * @param payload - Planner request.
 * @returns The planned timeline.
 */
export function planQuota(payload: {
  quota_count: number
  start_at?: string | null
  wake_at?: string | null
  machine_id?: number | null
}): Promise<QuotaPlan> {
  return api.post<QuotaPlan>('/api/v1/quota/plan', payload)
}
