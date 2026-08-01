import { api } from '~/services/api'

/**
 * Web Push notifications API service.
 * @module services/notificationsService
 */

/** The public VAPID key and whether push is configured server-side. */
export type VapidKey = {
  public_key: string | null
  configured: boolean
}

/** A browser push subscription payload sent to the server. */
export type PushSubscriptionPayload = {
  endpoint: string
  keys: { p256dh: string; auth: string }
  user_agent?: string
}

/** Diagnostic result of a test notification (delivered/failed = the push service's verdict). */
export type TestNotificationResult = {
  configured: boolean
  subscriptions: number
  delivered: number
  failed: number
  detail: string | null
}

/**
 * Fetch the public VAPID key needed to subscribe.
 * @returns The key and configured flag.
 */
export function getVapidKey(): Promise<VapidKey> {
  return api.get<VapidKey>('/api/v1/notifications/vapid-key')
}

/**
 * Register (or refresh) a browser push subscription.
 * @param payload - Endpoint + encryption keys + optional device hint.
 * @returns Nothing.
 */
export function subscribePush(payload: PushSubscriptionPayload): Promise<void> {
  return api.post('/api/v1/notifications/subscribe', payload)
}

/**
 * Remove a browser push subscription.
 * @param endpoint - The subscription endpoint.
 * @returns Nothing.
 */
export function unsubscribePush(endpoint: string): Promise<void> {
  return api.post('/api/v1/notifications/unsubscribe', { endpoint })
}

/**
 * Send a (delayed) test notification and get the diagnostic back.
 * @returns Whether push is configured, the device count, and the delay.
 */
export function testPush(): Promise<TestNotificationResult> {
  return api.post<TestNotificationResult>('/api/v1/notifications/test')
}
