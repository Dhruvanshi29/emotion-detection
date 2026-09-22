self.addEventListener('push', (event) => {
  let data = { title: 'A gentle reminder from Saaya', body: '', url: '/reminders' }
  try { data = { ...data, ...event.data.json() } } catch { /* use calm defaults */ }
  event.waitUntil(self.registration.showNotification(data.title, {
    body: data.body,
    icon: '/favicon.svg',
    badge: '/favicon.svg',
    data: { url: data.url },
    tag: 'saaya-reminder',
  }))
})

self.addEventListener('notificationclick', (event) => {
  event.notification.close()
  const url = event.notification.data?.url || '/reminders'
  event.waitUntil(clients.matchAll({ type: 'window', includeUncontrolled: true }).then((windows) => {
    const existing = windows.find((client) => 'focus' in client)
    return existing ? existing.focus().then(() => existing.navigate(url)) : clients.openWindow(url)
  }))
})
