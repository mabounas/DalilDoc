// Service worker de la borne.
//
// - Pages (navigation) : réseau d'abord, cache en secours hors ligne. Une page servie
//   depuis le cache référencerait d'anciens bundles : la borne ne se mettrait jamais à jour.
// - /_next/static/* : fichiers immuables (nom haché) → cache d'abord.
// - API : jamais mise en cache ici (le paquet hors ligne est géré par lib/offline.ts).
//
// Changer CACHE à chaque évolution de cette stratégie purge les anciens caches.
const CACHE = "wathiqadoc-shell-v2";
const SHELL = ["/", "/fr", "/ar", "/darija", "/en", "/pt", "/es"];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches
      .open(CACHE)
      .then((c) => c.addAll(SHELL))
      .catch(() => undefined) // hors ligne à l'installation : le cache se remplira à l'usage
      .then(() => self.skipWaiting()),
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
      .then(() => self.clients.claim()),
  );
});

self.addEventListener("fetch", (event) => {
  const { request } = event;
  const url = new URL(request.url);
  if (request.method !== "GET" || url.origin !== self.location.origin || url.pathname.startsWith("/api/")) return;

  if (request.mode === "navigate") {
    event.respondWith(
      fetch(request)
        .then((res) => {
          if (res.ok) caches.open(CACHE).then((c) => c.put(request, res.clone()));
          return res;
        })
        .catch(() => caches.match(request).then((cached) => cached || caches.match("/"))),
    );
    return;
  }

  if (url.pathname.startsWith("/_next/static/")) {
    event.respondWith(
      caches.match(request).then(
        (cached) =>
          cached ||
          fetch(request).then((res) => {
            if (res.ok) caches.open(CACHE).then((c) => c.put(request, res.clone()));
            return res;
          }),
      ),
    );
    return;
  }

  // Autres ressources (logo, manifest) : réseau d'abord, cache en secours.
  event.respondWith(
    fetch(request)
      .then((res) => {
        if (res.ok) caches.open(CACHE).then((c) => c.put(request, res.clone()));
        return res;
      })
      .catch(() => caches.match(request)),
  );
});
