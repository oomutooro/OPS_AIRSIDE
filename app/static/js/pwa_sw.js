const CACHE_NAME = 'airside-ops-v1';
const OFFLINE_ASSETS = [
  '/',
  '/static/css/main.css',
  '/static/css/forms.css',
  '/static/css/mobile.css',
  '/static/js/main.js',
  '/static/js/offline_sync.js'
];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(OFFLINE_ASSETS))
  );
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) => Promise.all(keys.filter((k) => k !== CACHE_NAME).map((k) => caches.delete(k))))
  );
});

self.addEventListener('fetch', (event) => {
  event.respondWith(
    caches.match(event.request).then((cached) => cached || fetch(event.request).catch(() => caches.match('/')))
  );
});
