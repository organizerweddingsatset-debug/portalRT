// Service Worker for Portal RT 09 PWA
const CACHE_NAME = 'portal-rt-cache-v1';
const CORE_ASSETS = [
  '/',
  '/static/css/tailwind.min.css',
  '/static/css/custom.css',
  '/static/img/logo_rt.svg',
  '/static/manifest.json',
  'https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.1/css/all.min.css'
];

// Install: Cache critical core shell assets
self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => {
      console.log('[SW] Caching app shell assets');
      return cache.addAll(CORE_ASSETS).catch((err) => {
        console.warn('[SW] Caching some assets failed:', err);
      });
    }).then(() => self.skipWaiting())
  );
});

// Activate: Purge old cache versions
self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((cacheNames) => {
      return Promise.all(
        cacheNames.map((name) => {
          if (name !== CACHE_NAME) {
            console.log('[SW] Deleting old cache:', name);
            return caches.delete(name);
          }
        })
      );
    }).then(() => self.clients.claim())
  );
});

// Fetch: Network-First for dynamic routes, Cache-First for static assets
self.addEventListener('fetch', (event) => {
  const request = event.request;
  const url = new URL(request.url);

  // Skip non-GET requests (POST form submissions, etc)
  if (request.method !== 'GET') {
    return;
  }

  // Static assets (CSS, JS, Fonts, SVG, Images) -> Cache-First
  if (
    url.pathname.startsWith('/static/') ||
    url.hostname.includes('cdnjs.cloudflare.com') ||
    url.hostname.includes('fonts.googleapis.com') ||
    url.hostname.includes('fonts.gstatic.com')
  ) {
    event.respondWith(
      caches.match(request).then((cachedResponse) => {
        if (cachedResponse) {
          return cachedResponse;
        }
        return fetch(request).then((networkResponse) => {
          if (networkResponse && networkResponse.status === 200) {
            const responseClone = networkResponse.clone();
            caches.open(CACHE_NAME).then((cache) => cache.put(request, responseClone));
          }
          return networkResponse;
        });
      })
    );
    return;
  }

  // Web pages (HTML navigation) -> Network-First with Cache Fallback
  event.respondWith(
    fetch(request)
      .then((networkResponse) => {
        if (networkResponse && networkResponse.status === 200) {
          const responseClone = networkResponse.clone();
          caches.open(CACHE_NAME).then((cache) => cache.put(request, responseClone));
        }
        return networkResponse;
      })
      .catch(async () => {
        const cachedResponse = await caches.match(request);
        if (cachedResponse) {
          return cachedResponse;
        }
        // Fallback response for offline status
        return new Response(
          `<!DOCTYPE html>
          <html lang="id">
          <head>
            <meta charset="UTF-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <title>Portal RT 09 - Mode Offline</title>
            <style>
              body { font-family: sans-serif; background: #0b0f1d; color: #fff; text-align: center; padding: 40px 20px; }
              .card { max-width: 420px; margin: 60px auto; background: #141b31; padding: 30px; border-radius: 12px; border: 1px solid #212c4e; }
              h1 { font-size: 20px; color: #818cf8; margin-bottom: 10px; }
              p { font-size: 13px; color: #94a3b8; line-height: 1.5; }
              button { background: #4f46e5; color: #fff; border: none; padding: 10px 20px; border-radius: 6px; font-weight: bold; cursor: pointer; margin-top: 15px; }
            </style>
          </head>
          <body>
            <div class="card">
              <h1>Portal RT 09 Offline</h1>
              <p>Perangkat Anda sedang tidak terhubung ke jaringan internet. Halaman ini memerlukan koneksi untuk sinkronisasi data terbaru.</p>
              <button onclick="window.location.reload()">Coba Muat Ulang</button>
            </div>
          </body>
          </html>`,
          {
            headers: { 'Content-Type': 'text/html; charset=utf-8' }
          }
        );
      })
  );
});
