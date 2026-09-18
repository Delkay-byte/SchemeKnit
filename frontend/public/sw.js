/**
 * SchemeKnit service worker — conservative, static-assets only.
 *
 * DELIBERATELY NOT CACHED, ever:
 *   - /api/*            (auth tokens, private API responses, school data)
 *   - generated lesson plans / documents / exports
 *   - any authenticated page HTML
 *
 * What IS cached:
 *   - same-origin static app shell assets (_next/static, /icons) using
 *     stale-while-revalidate, so an installed app opens fast.
 *
 * Navigation requests always go network-first: the user gets fresh HTML and
 * is never served a stale authenticated view. This is installability +
 * fast-open support, NOT full offline support — the app still requires a
 * network connection to sign in and work.
 */

const STATIC_CACHE = 'teachflow-static-v1';
const STATIC_ASSET = /\/_next\/static\/|\/icons\/|\/manifest\.webmanifest/;

self.addEventListener('install', (event) => {
  self.skipWaiting();
  event.waitUntil(
    caches.open(STATIC_CACHE).then((cache) =>
      cache.addAll(['/manifest.webmanifest', '/icons/icon-192.png', '/icons/icon-512.png'])
    )
  );
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== STATIC_CACHE).map((k) => caches.delete(k)))
    ).then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', (event) => {
  const req = event.request;
  if (req.method !== 'GET') return;

  const url = new URL(req.url);

  // Never touch the API or anything that is not same-origin static.
  if (url.origin !== self.location.origin) return;
  if (url.pathname.startsWith('/api/')) return;
  if (!STATIC_ASSET.test(url.pathname)) return;

  event.respondWith(
    caches.open(STATIC_CACHE).then((cache) =>
      cache.match(req).then((cached) => {
        const network = fetch(req)
          .then((res) => {
            if (res && res.status === 200) cache.put(req, res.clone());
            return res;
          })
          .catch(() => cached);
        return cached || network;
      })
    )
  );
});
