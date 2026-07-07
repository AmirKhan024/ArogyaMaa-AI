/*
 * ArogyaMaa ASHA — Service Worker
 *
 * Gives the ASHA field-worker dashboard an offline app shell. Field captures made while
 * offline are NOT handled here — offline-queue.js persists them in IndexedDB and replays
 * them to /asha/assessment when connectivity returns. The service worker only makes the UI
 * (HTML/CSS/JS + previously visited pages) load without a network.
 *
 * Strategy:
 *   - Precache the static app shell on install (CSS/JS/manifest/icons).
 *   - Same-origin /static/* and cross-origin CDN assets -> cache-first.
 *   - Navigations and other same-origin GETs -> network-first, falling back to cache, then
 *     to a minimal offline notice.
 *   - Never intercept non-GET requests (assessment POSTs go straight to the network / queue).
 *
 * Served from the app ROOT (/sw.js, with Service-Worker-Allowed: /) so its scope covers
 * /asha/dashboard/*. Bump CACHE_VERSION whenever a precached asset changes.
 */
'use strict';

const CACHE_VERSION = 'arogyamaa-asha-v1';
const STATIC_CACHE = CACHE_VERSION + '-static';
const RUNTIME_CACHE = CACHE_VERSION + '-runtime';

// App shell assets that are safe to precache (no auth required to fetch them).
const PRECACHE_URLS = [
  '/static/css/admin.css',
  '/static/js/admin_dashboard.js',
  '/static/js/offline-queue.js',
  '/static/manifest.webmanifest',
  '/static/icons/icon-192.png',
  '/static/icons/icon-512.png',
  '/static/icons/icon.svg',
];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(STATIC_CACHE)
      // addAll is atomic; use individual puts so one 404 can't abort the whole install.
      .then((cache) => Promise.all(
        PRECACHE_URLS.map((url) =>
          cache.add(url).catch((err) => console.warn('[sw] precache skipped', url, err))
        )
      ))
      .then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(
        keys.filter((k) => k !== STATIC_CACHE && k !== RUNTIME_CACHE)
            .map((k) => caches.delete(k))
      ))
      .then(() => self.clients.claim())
  );
});

function isStaticAsset(url) {
  return url.origin === self.location.origin && url.pathname.startsWith('/static/');
}

async function cacheFirst(request) {
  const cached = await caches.match(request);
  if (cached) return cached;
  try {
    const resp = await fetch(request);
    if (resp && (resp.ok || resp.type === 'opaque')) {
      const cache = await caches.open(STATIC_CACHE);
      cache.put(request, resp.clone());
    }
    return resp;
  } catch (err) {
    return cached || Response.error();
  }
}

async function networkFirst(request) {
  const cache = await caches.open(RUNTIME_CACHE);
  try {
    const resp = await fetch(request);
    if (resp && resp.ok && request.method === 'GET') {
      cache.put(request, resp.clone());
    }
    return resp;
  } catch (err) {
    const cached = await caches.match(request);
    if (cached) return cached;
    if (request.mode === 'navigate') {
      return new Response(
        '<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">' +
        '<title>Offline — ArogyaMaa</title>' +
        '<body style="font-family:Inter,system-ui,sans-serif;background:#1e3a5f;color:#fff;' +
        'display:flex;min-height:100vh;align-items:center;justify-content:center;text-align:center;margin:0">' +
        '<div><h1 style="margin:0 0 .5rem">You are offline</h1>' +
        '<p style="opacity:.8;max-width:24rem">This page has not been opened online yet. ' +
        'Assessments you submit now are saved on this device and will sync automatically ' +
        'when you are back online.</p></div></body>',
        { headers: { 'Content-Type': 'text/html; charset=utf-8' }, status: 503 }
      );
    }
    return Response.error();
  }
}

self.addEventListener('fetch', (event) => {
  const { request } = event;

  // Let non-GET requests (assessment POSTs, etc.) go straight to the network. Offline POSTs
  // are handled by the IndexedDB queue in the page, not by the service worker.
  if (request.method !== 'GET') return;

  const url = new URL(request.url);

  if (isStaticAsset(url) || url.origin !== self.location.origin) {
    event.respondWith(cacheFirst(request));
    return;
  }

  event.respondWith(networkFirst(request));
});

// Best-effort Background Sync: when the browser regains connectivity it wakes the SW, which
// tells any open client to flush its queue. The window 'online' listener is the reliable
// primary path; this is a bonus for when the tab is backgrounded.
self.addEventListener('sync', (event) => {
  if (event.tag === 'sync-assessments') {
    event.waitUntil(
      self.clients.matchAll({ includeUncontrolled: true }).then((clients) => {
        clients.forEach((client) => client.postMessage({ type: 'flush-queue' }));
      })
    );
  }
});
