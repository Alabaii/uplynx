const AUTH_TOKEN_KEY = 'uplynx.auth.token';
const AUTH_EXPIRES_AT_KEY = 'uplynx.auth.expiresAt';
const AUTH_EMAIL_KEY = 'uplynx.auth.email';
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

export function createSession(token: string, email?: string) {
  const expiresAt = decodeTokenExpiry(token) ?? now() + FALLBACK_SESSION_TTL_MS;

  sessionStorage.setItem(AUTH_TOKEN_KEY, token);
  sessionStorage.setItem(AUTH_EXPIRES_AT_KEY, String(expiresAt));

  if (email) {
    sessionStorage.setItem(AUTH_EMAIL_KEY, email);
  }
}

export function getAuthToken() {
  if (!hasValidSession()) {
    return null;
  }

  return sessionStorage.getItem(AUTH_TOKEN_KEY);
}

export function getSessionEmail() {
  return sessionStorage.getItem(AUTH_EMAIL_KEY);
}

export function clearSession() {
  sessionStorage.removeItem(AUTH_TOKEN_KEY);
  sessionStorage.removeItem(AUTH_EXPIRES_AT_KEY);
  sessionStorage.removeItem(AUTH_EMAIL_KEY);

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
