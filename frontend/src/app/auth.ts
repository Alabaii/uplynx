const AUTH_TOKEN_KEY = 'uplynx.auth.token';
const AUTH_EXPIRES_AT_KEY = 'uplynx.auth.expiresAt';
const AUTH_EMAIL_KEY = 'uplynx.auth.email';
// refresh живёт в localStorage: 30-дневная сессия переживает закрытие вкладки
const REFRESH_TOKEN_KEY = 'uplynx.auth.refreshToken';
const FALLBACK_SESSION_TTL_MS = 60 * 60 * 1000;

function now() {
  return Date.now();
}

function decodeTokenExpiry(token: string): number | null {
  try {
    const payload = token.split('.')[1];
    const json = JSON.parse(atob(payload.replace(/-/g, '+').replace(/_/g, '/')));

    return typeof json.exp === 'number' ? json.exp * 1000 : null;
  } catch {
    return null;
  }
}

export function createSession(token: string, email?: string, refreshToken?: string | null) {
  const expiresAt = decodeTokenExpiry(token) ?? now() + FALLBACK_SESSION_TTL_MS;

  sessionStorage.setItem(AUTH_TOKEN_KEY, token);
  sessionStorage.setItem(AUTH_EXPIRES_AT_KEY, String(expiresAt));

  if (email) {
    sessionStorage.setItem(AUTH_EMAIL_KEY, email);
  }

  if (refreshToken) {
    localStorage.setItem(REFRESH_TOKEN_KEY, refreshToken);
  }
}

export function startSession(token: string, email?: string, refreshToken?: string | null) {
  // вход и смена организации — момент, когда офлайн-кэш API относится уже к другому
  // владельцу данных: логаут его чистит, но пользователь может просто закрыть вкладку,
  // а следующий вход в офлайне показал бы мониторы предыдущего воркспейса
  clearOfflineApiCache();
  createSession(token, email, refreshToken);
}

export function getAuthToken() {
  if (!hasFreshAccessToken()) {
    return null;
  }

  return sessionStorage.getItem(AUTH_TOKEN_KEY);
}

export function getRefreshToken() {
  return localStorage.getItem(REFRESH_TOKEN_KEY);
}

export function getSessionEmail() {
  return sessionStorage.getItem(AUTH_EMAIL_KEY);
}

export function clearSession() {
  sessionStorage.removeItem(AUTH_TOKEN_KEY);
  sessionStorage.removeItem(AUTH_EXPIRES_AT_KEY);
  sessionStorage.removeItem(AUTH_EMAIL_KEY);
  localStorage.removeItem(REFRESH_TOKEN_KEY);

  // Clean up the previous mock auth value if it exists from older builds.
  localStorage.removeItem('token');

  clearOfflineApiCache();
}

// офлайн-кэш API живёт в service worker: токены убрали, а ответы с данными
// организации остались бы на устройстве до следующего входа
function clearOfflineApiCache() {
  // Сообщение доходит только когда страницей управляет активный worker. После
  // hard-reload и на первой загрузке (до clients.claim) controller === null, и
  // логаут молча не чистил НИЧЕГО: следующий вошедший на общем устройстве,
  // оказавшись офлайн, получал из кэша чужие мониторы, инциденты и аудит.
  // Caches доступен и самой странице — чистим напрямую, не полагаясь на worker.
  if ('caches' in window) {
    caches
      .keys()
      .then((names) =>
        Promise.all(names.filter((name) => name.startsWith('uplynx-api')).map((name) => caches.delete(name))),
      )
      .catch(() => {
        // приватный режим и запрет storage — чистить нечего
      });
  }

  if (!('serviceWorker' in navigator)) {
    return;
  }

  navigator.serviceWorker.controller?.postMessage({ type: 'clear-api-cache' });
}

function hasFreshAccessToken() {
  const token = sessionStorage.getItem(AUTH_TOKEN_KEY);
  const expiresAt = Number(sessionStorage.getItem(AUTH_EXPIRES_AT_KEY));

  return Boolean(token) && Number.isFinite(expiresAt) && expiresAt > now();
}

export function hasValidSession() {
  // живой access ИЛИ refresh: с коротким access сессию продлевает первый же
  // API-запрос (401 → refresh → повтор), выкидывать на /login рано
  if (hasFreshAccessToken()) {
    return true;
  }

  return Boolean(getRefreshToken());
}
