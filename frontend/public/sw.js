// Кэш статики и кэш данных API разделены намеренно:
//  - статика неизменна между сборками (хэш в имени) — её отдаём из кэша сразу;
//  - ответы API живые, их можно отдавать из кэша ТОЛЬКО когда сети нет, иначе
//    дашборд мониторинга показывал бы прошлый статус сервисов.
// В проде API отвечает с того же origin (nginx проксирует /api на backend),
// поэтому без явного разделения оба вида запросов попадают в один обработчик.
const STATIC_CACHE = 'uplynx-static-v2';
const API_CACHE = 'uplynx-api-v1';
const ACTIVE_CACHES = [STATIC_CACHE, API_CACHE];
const API_PREFIX = '/api/';

const STATIC_ASSETS = [
  '/',
  '/index.html',
  '/manifest.json'
];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(STATIC_CACHE)
      .then((cache) => cache.addAll(STATIC_ASSETS))
      .then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys()
      .then((cacheNames) => Promise.all(
        cacheNames
          .filter((cacheName) => !ACTIVE_CACHES.includes(cacheName))
          .map((cacheName) => caches.delete(cacheName))
      ))
      .then(() => self.clients.claim())
  );
});

// network-first: пока есть сеть, пользователь всегда видит актуальные данные;
// кэш — только запасной ответ для офлайн-режима (баннер про кэшированные данные)
async function apiNetworkFirst(request) {
  const cache = await caches.open(API_CACHE);

  try {
    const response = await fetch(request);

    if (response.ok) {
      cache.put(request, response.clone());
    }

    return response;
  } catch (error) {
    const cachedResponse = await cache.match(request);

    if (cachedResponse) {
      return cachedResponse;
    }

    throw error;
  }
}

async function staticStaleWhileRevalidate(request) {
  const cache = await caches.open(STATIC_CACHE);
  const cachedResponse = await cache.match(request);
  // офлайн при наличии кэша — обычная ситуация, ошибку фонового запроса гасим
  const networkResponse = fetch(request).then((response) => {
    if (response.ok) {
      cache.put(request, response.clone());
    }

    return response;
  });

  if (!cachedResponse) {
    return networkResponse;
  }

  networkResponse.catch(() => undefined);

  return cachedResponse;
}

self.addEventListener('fetch', (event) => {
  const requestUrl = new URL(event.request.url);

  if (event.request.method !== 'GET' || requestUrl.origin !== self.location.origin) {
    return;
  }

  if (event.request.mode === 'navigate') {
    event.respondWith(
      fetch(event.request).catch(() => caches.match('/index.html'))
    );
    return;
  }

  if (requestUrl.pathname.startsWith(API_PREFIX)) {
    event.respondWith(apiNetworkFirst(event.request));
    return;
  }

  event.respondWith(staticStaleWhileRevalidate(event.request));
});

// логаут: данные организации не должны оставаться на устройстве после выхода
self.addEventListener('message', (event) => {
  if (event.data && event.data.type === 'clear-api-cache') {
    event.waitUntil(caches.delete(API_CACHE));
  }
});

self.addEventListener('push', (event) => {
  let data = {};

  try {
    data = event.data ? event.data.json() : {};
  } catch {
    data = {};
  }

  const title = data.title || 'Uplynx Alert';
  const options = {
    body: data.body || 'One of your monitors changed status.',
    icon: '/icon-192x192.png',
    badge: '/icon-192x192.png',
    data: { url: data.url || '/' }
  };

  event.waitUntil(
    self.registration.showNotification(title, options)
  );
});

self.addEventListener('notificationclick', (event) => {
  event.notification.close();
  const url = (event.notification.data && event.notification.data.url) || '/';
  event.waitUntil(
    clients.openWindow(url)
  );
});
