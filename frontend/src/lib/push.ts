import { api } from './api'

type PushConfig = { enabled: boolean; public_key: string | null }

function decodeKey(value: string): Uint8Array<ArrayBuffer> {
  const padded = value + '='.repeat((4 - (value.length % 4)) % 4)
  const raw = atob(padded.replace(/-/g, '+').replace(/_/g, '/'))
  return Uint8Array.from(raw, (char) => char.charCodeAt(0)) as Uint8Array<ArrayBuffer>
}

export async function pushAvailability(): Promise<boolean> {
  if (!('serviceWorker' in navigator) || !('PushManager' in window) || !('Notification' in window)) return false
  const config = (await api.get<PushConfig>('/push/config')).data
  return config.enabled && !!config.public_key
}

export async function enablePush(): Promise<void> {
  const config = (await api.get<PushConfig>('/push/config')).data
  if (!config.enabled || !config.public_key) throw new Error('Push notifications are not configured')
  const permission = await Notification.requestPermission()
  if (permission !== 'granted') throw new Error('Notification permission was not granted')
  const registration = await navigator.serviceWorker.register('/sw.js')
  const subscription = await registration.pushManager.subscribe({
    userVisibleOnly: true,
    applicationServerKey: decodeKey(config.public_key),
  })
  const json = subscription.toJSON()
  if (!json.endpoint || !json.keys?.p256dh || !json.keys.auth) throw new Error('Browser returned an incomplete push subscription')
  await api.post('/push/subscriptions', { endpoint: json.endpoint, p256dh: json.keys.p256dh, auth: json.keys.auth })
}

export async function disablePush(): Promise<void> {
  const registration = await navigator.serviceWorker.getRegistration('/sw.js')
  const subscription = await registration?.pushManager.getSubscription()
  if (subscription) {
    await api.delete('/push/subscriptions', { data: { endpoint: subscription.endpoint } })
    await subscription.unsubscribe()
  }
}
