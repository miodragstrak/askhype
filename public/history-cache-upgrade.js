/* Retire the old broad runtime cache. Workbox continues to precache static assets. */
self.addEventListener('activate', (event) => {
  event.waitUntil(caches.delete('offlineCache'));
});
