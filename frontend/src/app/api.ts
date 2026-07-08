import { clearSession, getAuthToken } from './auth';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000/api/v1';

type RequestOptions = Omit<RequestInit, 'body'> & {
  body?: unknown;
  auth?: boolean;
};

export type MonitorType = 'http' | 'browser';
export type MonitorStatus = 'up' | 'down' | 'paused' | 'degraded' | 'pending';

export function getStatusLabel(status: MonitorStatus) {
  switch (status) {
    case 'up':
      return 'Up';
    case 'down':
      return 'Down';
    case 'paused':
      return 'Paused';
    case 'degraded':
      return 'Degraded';
    case 'pending':
      return 'Pending';
    default:
      return status;
  }
}

export type BrowserStep = {
  action: string;
  url?: string | null;
  selector?: string | null;
  text?: string | null;
  value?: string | null;
};

export type Monitor = {
  id: string;
  internal_id: number;
  name: string;
  type: MonitorType;
  status: MonitorStatus;
  url: string | null;
  interval: number;
  enabled: boolean;
  config: {
    expected?: {
      status?: number;
      body_contains?: string;
    };
    steps?: BrowserStep[];
  };
};

export type ConfigRead = {
  content: string;
  format: string;
  version: number | null;
};

export type ConfigVersion = {
  id: number;
  version: number;
  format: string;
  created_at: string;
};

export type CheckResult = {
  id: number;
  monitor_id: number;
  monitor_slug: string;
  status: MonitorStatus;
  response_time_ms: number | null;
  error: string | null;
  details: Record<string, unknown>;
  timestamp: string;
};

export class ApiError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const headers = new Headers(options.headers);
  const hasBody = options.body !== undefined;

  if (hasBody && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json');
  }

  if (options.auth !== false) {
    const token = getAuthToken();

    if (token) {
      headers.set('Authorization', `Bearer ${token}`);
    }
  }

  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...options,
    headers,
    body: hasBody ? JSON.stringify(options.body) : undefined,
  });

  if (response.status === 401 && options.auth !== false) {
    clearSession();

    if (!window.location.pathname.startsWith('/login')) {
      window.location.assign('/login');
    }
  }

  if (!response.ok) {
    let message = response.statusText;

    try {
      const payload = await response.json();
      message = typeof payload.detail === 'string' ? payload.detail : JSON.stringify(payload.detail ?? payload);
    } catch {
      // Keep status text when backend did not return JSON.
    }

    throw new ApiError(response.status, message);
  }

  if (response.status === 204) {
    return undefined as T;
  }

  return response.json() as Promise<T>;
}

export function register(email: string, password: string) {
  return request<{ id: number; email: string }>('/auth/register', {
    method: 'POST',
    body: { email, password },
    auth: false,
  });
}

export function login(email: string, password: string) {
  return request<{ access_token: string; token_type: string }>('/auth/login', {
    method: 'POST',
    body: { email, password },
    auth: false,
  });
}

export type OrganizationInfo = {
  id: number;
  name: string;
  slug: string;
  role: string;
};

export function getMe() {
  return request<{ id: number; email: string; organization?: OrganizationInfo }>('/auth/me');
}

export function listMonitors() {
  return request<Monitor[]>('/monitors');
}

export function getMonitor(id: string) {
  return request<Monitor>(`/monitors/${encodeURIComponent(id)}`);
}

export function createMonitor(payload: {
  id: string;
  name: string;
  type: MonitorType;
  url?: string;
  interval: number;
  expected?: { status?: number; body_contains?: string };
  steps?: BrowserStep[];
}) {
  return request<Monitor>('/monitors', {
    method: 'POST',
    body: payload,
  });
}

export function getConfig() {
  return request<ConfigRead>('/config');
}

export function uploadConfig(content: string, format: 'yaml' | 'json') {
  return request<ConfigVersion>('/config', {
    method: 'POST',
    body: { content, format },
  });
}

export function listConfigVersions() {
  return request<ConfigVersion[]>('/config/versions');
}

export function rollbackConfig(version: number) {
  return request<ConfigVersion>('/config/rollback', {
    method: 'POST',
    body: { version },
  });
}

export function getHistory(params: { monitorId?: string; range?: string; status?: MonitorStatus } = {}) {
  const search = new URLSearchParams();

  if (params.monitorId) search.set('monitor_id', params.monitorId);
  if (params.range) search.set('range', params.range);
  if (params.status) search.set('status', params.status);

  return request<CheckResult[]>(`/history${search.size ? `?${search.toString()}` : ''}`);
}

export type TelegramIntegration = {
  connected: boolean;
  chat_id: string | null;
  alert_scopes: string[];
  bot_token_masked?: string | null;
};

export function getTelegram() {
  return request<TelegramIntegration>('/telegram');
}

export function connectTelegram(payload: { bot_token: string; chat_id: string; alert_scopes: string[] }) {
  return request<TelegramIntegration>('/telegram/connect', {
    method: 'POST',
    body: payload,
  });
}

export function testTelegram() {
  return request<{ ok: boolean; detail: string }>('/telegram/test', {
    method: 'POST',
  });
}
