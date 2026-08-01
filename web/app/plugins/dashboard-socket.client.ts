import { watch } from 'vue'

/**
 * Dashboard WebSocket — subscribes to the control-plane's live feed and keeps the
 * session-activity store fresh, so the Discussions spinner is instant (no polling).
 */
export default defineNuxtPlugin(() => {
  const config = useRuntimeConfig()
  const userStore = useUserStore()
  const activity = useSessionActivityStore()

  let socket: WebSocket | null = null
  let reconnectTimer: ReturnType<typeof setTimeout> | null = null
  let backoffMs = 1000
  let disposed = false

  /**
   * Build the dashboard WebSocket URL with the current JWT.
   * @param token - The user access token.
   * @returns The ws(s):// URL.
   */
  function socketUrl(token: string): string {
    const base = String(config.public.apiBase).replace(/^http/, 'ws')
    return `${base}/api/v1/ws/dashboard?token=${encodeURIComponent(token)}`
  }

  /**
   * Schedule a reconnection with exponential backoff (capped).
   * @returns Nothing.
   */
  function scheduleReconnect(): void {
    if (disposed) {
      return
    }
    if (reconnectTimer) {
      clearTimeout(reconnectTimer)
    }
    reconnectTimer = setTimeout(connect, backoffMs)
    backoffMs = Math.min(backoffMs * 2, 30000)
  }

  /**
   * Open the dashboard socket (retrying until authenticated, reconnecting on drop).
   * @returns Nothing.
   */
  function connect(): void {
    if (disposed) {
      return
    }
    const token = userStore.token
    if (!token) {
      reconnectTimer = setTimeout(connect, 2000)
      return
    }
    try {
      socket = new WebSocket(socketUrl(token))
    } catch {
      scheduleReconnect()
      return
    }
    socket.onopen = (): void => {
      backoffMs = 1000
    }
    socket.onmessage = (event: MessageEvent): void => {
      try {
        const data = JSON.parse(event.data)
        if (
          data?.type === 'sessions.active' &&
          typeof data.machine_id === 'number' &&
          Array.isArray(data.session_ids)
        ) {
          activity.setActive(data.machine_id, data.session_ids.map(String))
        }
      } catch {
        // Ignore non-JSON / irrelevant frames.
      }
    }
    socket.onclose = (): void => {
      socket = null
      scheduleReconnect()
    }
    socket.onerror = (): void => {
      socket?.close()
    }
  }

  connect()

  // Reconnect with the new identity on login / logout.
  watch(
    () => userStore.token,
    (): void => {
      socket?.close()
      if (reconnectTimer) {
        clearTimeout(reconnectTimer)
      }
      backoffMs = 1000
      connect()
    },
  )

  if (import.meta.hot) {
    import.meta.hot.dispose(() => {
      disposed = true
      socket?.close()
      if (reconnectTimer) {
        clearTimeout(reconnectTimer)
      }
    })
  }
})
