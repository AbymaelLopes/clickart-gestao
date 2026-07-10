const CACHE_NAME = 'clickart-cache-v2'; // Mudei para v2 (sempre que mudar algo visual, incremente isso!)

const urlsToCache = [
  './index.html',
  './manifest.json'
];

// Instala e ativa imediatamente
self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(CACHE_NAME).then(cache => cache.addAll(urlsToCache))
  );
  self.skipWaiting(); // <--- FORÇA O NOVO SW A ASSUMIR
});

self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys().then(cacheNames => {
      return Promise.all(
        cacheNames.filter(name => name !== CACHE_NAME).map(name => caches.delete(name))
      );
    })
  );
  event.waitUntil(clients.claim()); // <--- CONTROLA AS ABAS ABERTAS
});

self.addEventListener('fetch', event => {
  if (event.request.url.includes('supabase.co')) return;

  event.respondWith(
    // Estratégia de Network First (Tenta buscar na rede, se falhar, usa o cache)
    fetch(event.request)
      .catch(() => caches.match(event.request))
  );
});