/**
 * PushNotifications – header button to subscribe/unsubscribe from Web Push.
 *
 * Shows a Bell icon. On click:
 *  1. Requests Notification permission if not yet granted.
 *  2. Fetches the VAPID public key from the backend.
 *  3. Subscribes (or unsubscribes) via the PushManager.
 *  4. Registers the subscription with the backend.
 *
 * The button is hidden when push notifications are not supported by the browser
 * or when HTTPS is not active (push requires a secure context).
 */

import { useState, useEffect } from 'react'
import { Bell, BellOff } from 'lucide-react'
import { useToast } from './Toast'

function urlBase64ToUint8Array(base64String) {
  const padding = '='.repeat((4 - (base64String.length % 4)) % 4)
  const base64 = (base64String + padding).replace(/-/g, '+').replace(/_/g, '/')
  const raw = atob(base64)
  return Uint8Array.from([...raw].map((c) => c.charCodeAt(0)))
}

async function getVapidPublicKey() {
  const res = await fetch('/api/push/vapid-public-key')
  if (!res.ok) throw new Error(`VAPID key unavailable (${res.status})`)
  const { publicKey } = await res.json()
  return publicKey
}

async function sendSubscriptionToBackend(subscription, method = 'POST') {
  const res = await fetch('/api/push/subscribe', {
    method,
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(subscription.toJSON()),
  })
  if (!res.ok) throw new Error(`Backend subscription ${method} failed (${res.status})`)
}

function usePushSubscription() {
  const [subscription, setSubscription] = useState(null)
  const [supported, setSupported] = useState(false)
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    const ok =
      'serviceWorker' in navigator &&
      'PushManager' in window &&
      window.isSecureContext
    setSupported(ok)

    if (ok) {
      navigator.serviceWorker.ready
        .then((reg) => reg.pushManager.getSubscription())
        .then(setSubscription)
        .catch((err) => console.error('[Push] Failed to read existing subscription:', err))
    }
  }, [])

  return { subscription, setSubscription, supported, loading, setLoading }
}

function PushNotifications() {
  const toast = useToast()
  const { subscription, setSubscription, supported, loading, setLoading } = usePushSubscription()

  if (!supported) return null

  const isSubscribed = subscription !== null

  async function handleSubscribe() {
    setLoading(true)
    try {
      const permission = await Notification.requestPermission()
      if (permission !== 'granted') {
        toast('Notification permission denied', 'error')
        return
      }

      const publicKey = await getVapidPublicKey()
      const reg = await navigator.serviceWorker.ready
      const sub = await reg.pushManager.subscribe({
        userVisibleOnly: true,
        applicationServerKey: urlBase64ToUint8Array(publicKey),
      })

      await sendSubscriptionToBackend(sub, 'POST')
      setSubscription(sub)
      toast('Push notifications enabled', 'success')
    } catch (err) {
      toast(err.message || 'Failed to enable push notifications', 'error')
    } finally {
      setLoading(false)
    }
  }

  async function handleUnsubscribe() {
    setLoading(true)
    try {
      // Revoke at browser/push-service level first; backend cleanup is idempotent
      await subscription.unsubscribe()
      await sendSubscriptionToBackend(subscription, 'DELETE')
      setSubscription(null)
      toast('Push notifications disabled', 'success')
    } catch (err) {
      toast(err.message || 'Failed to disable push notifications', 'error')
    } finally {
      setLoading(false)
    }
  }

  return (
    <button
      data-testid="push-notifications-btn"
      onClick={isSubscribed ? handleUnsubscribe : handleSubscribe}
      disabled={loading}
      title={isSubscribed ? 'Disable push notifications' : 'Enable push notifications'}
      className={[
        'flex items-center gap-1.5 px-2.5 py-1.5 rounded-md text-sm font-medium transition-colors flex-shrink-0',
        'border',
        isSubscribed
          ? 'bg-primary/10 border-primary/30 text-primary hover:bg-primary/20'
          : 'bg-transparent border-border text-text-secondary hover:bg-surface hover:text-text-primary',
        loading && 'opacity-60 cursor-not-allowed',
      ]
        .filter(Boolean)
        .join(' ')}
      aria-pressed={isSubscribed}
    >
      {isSubscribed ? (
        <Bell size={15} className="flex-shrink-0" />
      ) : (
        <BellOff size={15} className="flex-shrink-0" />
      )}
      <span className="hidden md:inline">{isSubscribed ? 'Notifs on' : 'Notifs off'}</span>
    </button>
  )
}

export default PushNotifications
