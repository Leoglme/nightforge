/**
 * Web Push helpers shared by the composable (dashboard switch) and the auto-subscribe plugin.
 * @module utils/webPush
 */
import { getVapidKey, subscribePush, unsubscribePush } from '~/services/notificationsService'

/** localStorage flag: the user turned notifications off, so don't auto-resubscribe. */
const DISABLED_KEY = 'nf-push-disabled'

/**
 * Whether this browser can do Web Push at all.
 * @returns True if supported.
 */
export function isPushSupported(): boolean {
  return import.meta.client && 'serviceWorker' in navigator && 'PushManager' in window && 'Notification' in window
}

/**
 * Whether the app runs as an installed PWA (required for push on iOS).
 * @returns True in standalone display mode.
 */
export function isStandalonePwa(): boolean {
  if (!import.meta.client) {
    return false
  }
  const iosStandalone = (window.navigator as Navigator & { standalone?: boolean }).standalone === true
  return window.matchMedia('(display-mode: standalone)').matches || iosStandalone
}

/**
 * Whether the user explicitly turned notifications off on this device.
 * @returns True if disabled locally.
 */
export function isPushDisabledLocally(): boolean {
  return import.meta.client && window.localStorage.getItem(DISABLED_KEY) === '1'
}

/**
 * Persist the user's on/off choice so auto-subscribe respects it.
 * @param disabled - Whether notifications are turned off.
 * @returns Nothing.
 */
function setDisabledLocally(disabled: boolean): void {
  if (!import.meta.client) {
    return
  }
  if (disabled) {
    window.localStorage.setItem(DISABLED_KEY, '1')
  } else {
    window.localStorage.removeItem(DISABLED_KEY)
  }
}

/**
 * Decode a base64url VAPID key into the bytes the Push API expects.
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
 * Whether an active push subscription exists (permission granted + subscription present).
 * @returns True if subscribed.
 */
export async function isPushSubscribed(): Promise<boolean> {
  if (!isPushSupported() || Notification.permission !== 'granted') {
    return false
  }
  const registration = await navigator.serviceWorker.getRegistration()
  const subscription = registration ? await registration.pushManager.getSubscription() : null
  return Boolean(subscription)
}

/**
 * Register the service worker, subscribe to push and persist it server-side.
 * Assumes notification permission is already granted.
 * @returns True on success.
 */
export async function subscribeToPush(): Promise<boolean> {
  if (!isPushSupported()) {
    return false
  }
  const vapid = await getVapidKey()
  if (!vapid.configured || !vapid.public_key) {
    return false
  }
  const registration = await navigator.serviceWorker.register('/sw.js')
  await navigator.serviceWorker.ready
  let subscription = await registration.pushManager.getSubscription()
  if (!subscription) {
    subscription = await registration.pushManager.subscribe({
      userVisibleOnly: true,
      applicationServerKey: urlBase64ToUint8Array(vapid.public_key),
    })
  }
  const json = subscription.toJSON()
  if (!json.endpoint || !json.keys?.p256dh || !json.keys?.auth) {
    return false
  }
  await subscribePush({
    endpoint: json.endpoint,
    keys: { p256dh: json.keys.p256dh, auth: json.keys.auth },
    user_agent: navigator.userAgent.slice(0, 400),
  })
  setDisabledLocally(false)
  return true
}

/**
 * Unsubscribe this device and remember the choice (temporary disable).
 * @returns Nothing.
 */
export async function unsubscribeFromPush(): Promise<void> {
  setDisabledLocally(true)
  if (!isPushSupported()) {
    return
  }
  const registration = await navigator.serviceWorker.getRegistration()
  const subscription = registration ? await registration.pushManager.getSubscription() : null
  if (subscription) {
    await unsubscribePush(subscription.endpoint).catch(() => {})
    await subscription.unsubscribe()
  }
}
