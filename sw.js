const CACHE_NAME = 'clickart-cache-v1';

const urlsToCache = [
  './index.html',
  './manifest.json'
];

self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(CACHE_NAME).then(cache => cache.addAll(urlsToCache))
  );
});

self.addEventListener('fetch', event => {
  // ADICIONAMOS: Ignora qualquer requisição para o Supabase
  if (event.request.url.includes('supabase.co')) {
    return; // O navegador vai direto na rede (Network) sem consultar o cache
  }

  // Ignora outras APIs se necessário
  if (event.request.url.includes('127.0.0.1:8000') || event.request.url.includes('api')) {
    return;
  }

  event.respondWith(
    caches.match(event.request).then(response => {
      return response || fetch(event.request);
    })
  );
});

self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys().then(cacheNames => {
      return Promise.all(
        cacheNames.filter(name => name !== CACHE_NAME).map(name => caches.delete(name))
      );
    })
  );
});