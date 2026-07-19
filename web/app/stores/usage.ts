import { defineStore } from 'pinia'
import { ref } from 'vue'
import type { UsageSummary } from '~/types'
import { fetchUsageSummary } from '~/services/quotaService'

/**
 * Cached account usage (Claude / Cursor) — loaded on demand, not on every navigation.
 * @module stores/usage
 */
export const useUsageStore = defineStore('usage', () => {
  const usage = ref<UsageSummary | null>(null)
  const loading = ref(false)
  const loaded = ref(false)
  const error = ref<string | null>(null)

  /**
   * Fetch usage from the API (live agent read when available).
   */
  async function refresh(): Promise<void> {
    if (loading.value) return
    loading.value = true
    error.value = null
    try {
      usage.value = await fetchUsageSummary()
      loaded.value = true
    } catch (err) {
      error.value = err instanceof Error ? err.message : 'Lecture usage impossible'
      if (!loaded.value) {
        usage.value = null
      }
    } finally {
      loading.value = false
    }
  }

  /**
   * Load once if never fetched (keeps cache when navigating away and back).
   */
  async function ensureLoaded(): Promise<void> {
    if (loaded.value || loading.value) return
    await refresh()
  }

  return { usage, loading, loaded, error, refresh, ensureLoaded }
})
