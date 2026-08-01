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
 * Send a test notification to the current user's devices.
 * @returns Nothing.
 */
export function testPush(): Promise<void> {
  return api.post('/api/v1/notifications/test')
}
