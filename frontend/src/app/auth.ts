const AUTH_TOKEN_KEY = 'uplynx.auth.token';
const AUTH_EXPIRES_AT_KEY = 'uplynx.auth.expiresAt';
const MOCK_SESSION_TTL_MS = 60 * 60 * 1000;

function now() {
  return Date.now();
}

function createSessionToken() {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID();
  }

  return `mock-${now().toString(36)}-${Math.random().toString(36).slice(2, 12)}`;
}

export function createMockSession() {
  const expiresAt = now() + MOCK_SESSION_TTL_MS;

  sessionStorage.setItem(AUTH_TOKEN_KEY, createSessionToken());
  sessionStorage.setItem(AUTH_EXPIRES_AT_KEY, String(expiresAt));
}

export function clearSession() {
  sessionStorage.removeItem(AUTH_TOKEN_KEY);
  sessionStorage.removeItem(AUTH_EXPIRES_AT_KEY);

  // Clean up the previous mock auth value if it exists from older builds.
  localStorage.removeItem('token');
}

export function hasValidSession() {
  const token = sessionStorage.getItem(AUTH_TOKEN_KEY);
  const expiresAt = Number(sessionStorage.getItem(AUTH_EXPIRES_AT_KEY));

  if (!token || !Number.isFinite(expiresAt) || expiresAt <= now()) {
    clearSession();
    return false;
  }

  return true;
}
