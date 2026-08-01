import { defineStore } from 'pinia'
import { computed, ref } from 'vue'

/**
 * Live "which sessions are working" state, pushed by agents over the dashboard WebSocket.
 * @module stores/sessionActivity
 */
export const useSessionActivityStore = defineStore('sessionActivity', () => {
  /** In-progress session ids per machine (replaced wholesale on each push). */
  const activeByMachine = ref<Record<number, string[]>>({})

  /** Flat set of all active session ids across machines. */
  const activeSessionIds = computed(() => new Set(Object.values(activeByMachine.value).flat()))

  /**
   * Replace a machine's active session ids from a WebSocket push.
   * @param machineId - The reporting machine.
   * @param sessionIds - Its current in-progress session ids.
   * @returns Nothing.
   */
  function setActive(machineId: number, sessionIds: string[]): void {
    activeByMachine.value = { ...activeByMachine.value, [machineId]: sessionIds }
  }

  /**
   * Whether a session is currently working (per the live feed).
   * @param sessionId - The Claude session id.
   * @returns True while active.
   */
  function isActive(sessionId: string): boolean {
    return activeSessionIds.value.has(sessionId)
  }

  return { activeByMachine, activeSessionIds, setActive, isActive }
})
