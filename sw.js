const CACHE_NAME = 'clickart-cache-v1';

// Arquivos que o app vai salvar na memória do celular
const urlsToCache = [
  './index.html',
  './manifest.json'
];

// Evento de Instalação: Salva os arquivos no cache
self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then(cache => {
        console.log('Cache do ClickArt aberto com sucesso');
        return cache.addAll(urlsToCache);
      })
  );
});

// Evento de Interceptação: Busca no cache primeiro
self.addEventListener('fetch', event => {
  // Ignora requisições para a API do FastAPI (pois os dados sempre devem ser reais)
  if (event.request.url.includes('127.0.0.1:8000') || event.request.url.includes('api')) {
    return;
  }

  event.respondWith(
    caches.match(event.request)
      .then(response => {
        // Retorna o arquivo do cache se encontrar; caso contrário, busca na rede
        return response || fetch(event.request);
      })
  );
});

// Evento de Atualização: Limpa caches antigos se mudarmos a versão (v1 para v2)
self.addEventListener('activate', event => {
  const cacheWhitelist = [CACHE_NAME];
  event.waitUntil(
    caches.keys().then(cacheNames => {
      return Promise.all(
        cacheNames.map(cacheName => {
          if (cacheWhitelist.indexOf(cacheName) === -1) {
            return caches.delete(cacheName);
          }
        })
      );
    })
  );
});