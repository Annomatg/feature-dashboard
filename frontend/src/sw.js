/**
 * Custom Service Worker for Feature Dashboard PWA
 *
 * Handles:
 *  - Workbox precaching (manifest injected by vite-plugin-pwa)
 *  - Runtime caching for /api/ routes (excluding push endpoints)
 *  - Web Push notifications
 *  - Notification click navigation
 */

import { precacheAndRoute, cleanupOutdatedCaches } from 'workbox-precaching'
import { registerRoute } from 'workbox-routing'
import { NetworkFirst } from 'workbox-strategies'
import { CacheableResponsePlugin } from 'workbox-cacheable-response'
import { ExpirationPlugin } from 'workbox-expiration'

// Precache all assets (manifest is injected by vite-plugin-pwa at build time)
precacheAndRoute(self.__WB_MANIFEST)
cleanupOutdatedCaches()

// Runtime caching: API routes – network first, fall back to cache.
// Push subscription/notification endpoints are excluded (non-idempotent, not useful to cache).
registerRoute(
  ({ url }) =>
    url.pathname.startsWith('/api/') && !url.pathname.startsWith('/api/push/'),
  new NetworkFirst({
    cacheName: 'api-cache',
    networkTimeoutSeconds: 5,
    plugins: [
      new CacheableResponsePlugin({ statuses: [0, 200] }),
      new ExpirationPlugin({ maxEntries: 50, maxAgeSeconds: 60 * 60 }),
    ],
  })
)

// ---------------------------------------------------------------------------
// Push Notifications
// ---------------------------------------------------------------------------

self.addEventListener('push', (event) => {
  if (!event.data) return

  let data
  try {
    data = event.data.json()
  } catch {
    data = { title: 'Feature Dashboard', body: event.data.text() }
  }

  const title = data.title || 'Feature Dashboard'
  const options = {
    body: data.body || 'A task has completed.',
    icon: '/pwa-192x192.png',
    badge: '/pwa-64x64.png',
    tag: data.tag || 'feature-notification',
    renotify: true,
    data: { url: data.url || '/' },
  }

  event.waitUntil(self.registration.showNotification(title, options))
})

self.addEventListener('notificationclick', (event) => {
  event.notification.close()

  const targetUrl = event.notification.data?.url || '/'

  event.waitUntil(
    clients.matchAll({ type: 'window', includeUncontrolled: true }).then((clientList) => {
      for (const client of clientList) {
        if ('focus' in client) {
          // Focus the existing window, then navigate if needed
          return client.focus().then((focused) => {
            if (focused && focused.url !== targetUrl) {
              focused.navigate(targetUrl)
            }
          })
        }
      }
      if (clients.openWindow) {
        return clients.openWindow(targetUrl)
      }
    })
  )
})
