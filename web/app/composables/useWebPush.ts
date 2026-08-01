import { onMounted, ref, type Ref } from 'vue'
import { getVapidKey, subscribePush, testPush, unsubscribePush } from '~/services/notificationsService'

/** Reactive state and actions for enabling Web Push on the mobile PWA. */
export type UseWebPush = {
  supported: Ref<boolean>
  standalone: Ref<boolean>
  subscribed: Ref<boolean>
  busy: Ref<boolean>
  error: Ref<string | null>
  enable: () => Promise<void>
  disable: () => Promise<void>
  sendTest: () => Promise<void>
}

/**
 * Decode a base64url VAPID key into the byte array the Push API expects.
 * @param base64 - The base64url application-server key.
 * @returns The decoded bytes.
 */
function urlBase64ToUint8Array(base64: string): Uint8Array {
  const padding = '='.repeat((4 - (base64.length % 4)) % 4)
  const normalized = (base64 + padding).replace(/-/g, '+').replace(/_/g, '/')
  const raw = atob(normalized)
  const output = new Uint8Array(raw.length)
  for (let index = 0; index < raw.length; index += 1) {
    output[index] = raw.charCodeAt(index)
  }
  return output
}

/**
 * Manage Web Push subscription for the current device.
 * @returns Support flags, subscription state and enable/disable/test actions.
 */
export function useWebPush(): UseWebPush {
  const supported = ref(false)
  const standalone = ref(false)
  const subscribed = ref(false)
  const busy = ref(false)
  const error = ref<string | null>(null)

  /**
   * Read the current support / subscription state.
   * @returns Nothing.
   */
  async function refreshState(): Promise<void> {
    if (!import.meta.client) {
      return
    }
    supported.value = 'serviceWorker' in navigator && 'PushManager' in window && 'Notification' in window
    const iosStandalone = (window.navigator as Navigator & { standalone?: boolean }).standalone === true
    standalone.value = window.matchMedia('(display-mode: standalone)').matches || iosStandalone
    if (!supported.value) {
      return
    }
    try {
      const registration = await navigator.serviceWorker.getRegistration()
      const subscription = registration ? await registration.pushManager.getSubscription() : null
      subscribed.value = Boolean(subscription) && Notification.permission === 'granted'
    } catch {
      subscribed.value = false
    }
  }

  /**
   * Request permission, register the service worker and subscribe to push.
   * @returns Nothing.
   */
  async function enable(): Promise<void> {
    if (!supported.value || busy.value) {
      return
    }
    busy.value = true
    error.value = null
    try {
      const permission = await Notification.requestPermission()
      if (permission !== 'granted') {
        error.value = 'permission'
        return
      }
      const vapid = await getVapidKey()
      if (!vapid.configured || !vapid.public_key) {
        error.value = 'not-configured'
        return
      }
      const registration = await navigator.serviceWorker.register('/sw.js')
      await navigator.serviceWorker.ready
      const subscription = await registration.pushManager.subscribe({
        userVisibleOnly: true,
        applicationServerKey: urlBase64ToUint8Array(vapid.public_key),
      })
      const json = subscription.toJSON()
      if (!json.endpoint || !json.keys?.p256dh || !json.keys?.auth) {
        error.value = 'subscription'
        return
      }
      await subscribePush({
        endpoint: json.endpoint,
        keys: { p256dh: json.keys.p256dh, auth: json.keys.auth },
        user_agent: navigator.userAgent.slice(0, 400),
      })
      subscribed.value = true
    } catch (err) {
      error.value = err instanceof Error ? err.message : 'error'
    } finally {
      busy.value = false
    }
  }

  /**
   * Unsubscribe this device from push.
   * @returns Nothing.
   */
  async function disable(): Promise<void> {
    if (busy.value) {
      return
    }
    busy.value = true
    error.value = null
    try {
      const registration = await navigator.serviceWorker.getRegistration()
      const subscription = registration ? await registration.pushManager.getSubscription() : null
      if (subscription) {
        await unsubscribePush(subscription.endpoint).catch(() => {})
        await subscription.unsubscribe()
      }
      subscribed.value = false
    } catch (err) {
      error.value = err instanceof Error ? err.message : 'error'
    } finally {
      busy.value = false
    }
  }

  /**
   * Send a test notification to this user's devices.
   * @returns Nothing.
   */
  async function sendTest(): Promise<void> {
    await testPush()
  }

  onMounted(refreshState)

  return { supported, standalone, subscribed, busy, error, enable, disable, sendTest }
}
