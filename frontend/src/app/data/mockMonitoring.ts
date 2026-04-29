export type MonitorType = 'http' | 'browser';
export type MonitorStatus = 'up' | 'down' | 'paused' | 'degraded';
export type BrowserStepAction = 'goto' | 'click' | 'type' | 'assert_text';
export type AlertSeverity = 'info' | 'warning' | 'critical';

export interface Group {
  id: string;
  name: string;
  role: 'owner' | 'editor' | 'viewer';
}

export interface User {
  id: string;
  name: string;
  email: string;
  initials: string;
  activeGroupId: string;
}

export interface BrowserStep {
  id: string;
  action: BrowserStepAction;
  label: string;
  url?: string;
  selector?: string;
  value?: string;
  expectedText?: string;
}

export interface MonitorExpected {
  status?: number;
  bodyContains?: string;
}

export interface Monitor {
  id: string;
  name: string;
  type: MonitorType;
  status: MonitorStatus;
  url: string;
  intervalSeconds: number;
  location: string;
  groupId?: string;
  tags: string[];
  uptime24h: number;
  responseTimeMs: number | null;
  lastCheckedAt: string;
  lastIncidentAt?: string;
  summary: string;
  expected?: MonitorExpected;
  steps?: BrowserStep[];
}

export interface CheckResult {
  id: string;
  monitorId: string;
  timestamp: string;
  status: MonitorStatus;
  responseTimeMs: number | null;
  error?: string;
  location: string;
  logLines: string[];
}

export interface Incident {
  id: string;
  monitorId: string;
  title: string;
  severity: AlertSeverity;
  startedAt: string;
  resolvedAt?: string;
  impact: string;
}

export interface ConfigVersion {
  id: string;
  version: number;
  createdAt: string;
  author: string;
  summary: string;
  content: string;
}

export interface TelegramIntegration {
  connected: boolean;
  botName: string;
  chatId: string;
  alerts: Array<'down' | 'degraded' | 'recovered'>;
  lastTestAt?: string;
}

export interface ResponsePoint {
  label: string;
  responseTimeMs: number;
  status: MonitorStatus;
}

const monitorHealthTimeline: Record<string, MonitorStatus[]> = {
  'api-health': [
    'up', 'up', 'up', 'up', 'up', 'up', 'up', 'up', 'up', 'up',
    'up', 'up', 'up', 'up', 'up', 'up', 'up', 'up', 'up', 'up',
  ],
  'marketing-home': [
    'up', 'up', 'up', 'up', 'up', 'up', 'degraded', 'degraded', 'up', 'up',
    'up', 'up', 'up', 'degraded', 'degraded', 'up', 'up', 'up', 'up', 'up',
  ],
  'checkout-flow': [
    'up', 'up', 'up', 'up', 'up', 'down', 'down', 'down', 'up', 'up',
    'down', 'down', 'down', 'down', 'down', 'up', 'up', 'down', 'down', 'down',
  ],
  'staging-login': [
    'paused', 'paused', 'paused', 'paused', 'paused', 'paused', 'paused', 'paused', 'paused', 'paused',
    'paused', 'paused', 'paused', 'paused', 'paused', 'paused', 'paused', 'paused', 'paused', 'paused',
  ],
};

const groups: Group[] = [
  { id: 'grp-core', name: 'Core Platform', role: 'owner' },
  { id: 'grp-growth', name: 'Growth Sites', role: 'editor' },
];

const currentUser: User = {
  id: 'usr-01',
  name: 'Julia Dovzhenko',
  email: 'julia@uplynx.app',
  initials: 'JD',
  activeGroupId: 'grp-core',
};

const monitors: Monitor[] = [
  {
    id: 'api-health',
    name: 'Production API Health',
    type: 'http',
    status: 'up',
    url: 'https://api.example.com/health',
    intervalSeconds: 60,
    location: 'eu-central-1',
    groupId: 'grp-core',
    tags: ['backend', 'p0'],
    uptime24h: 99.98,
    responseTimeMs: 124,
    lastCheckedAt: '2026-04-30T10:43:00Z',
    summary: 'HTTP health endpoint with body assertion for "ok".',
    expected: { status: 200, bodyContains: 'ok' },
  },
  {
    id: 'marketing-home',
    name: 'Marketing Homepage',
    type: 'http',
    status: 'degraded',
    url: 'https://example.com',
    intervalSeconds: 120,
    location: 'eu-west-1',
    groupId: 'grp-growth',
    tags: ['frontend', 'seo'],
    uptime24h: 99.35,
    responseTimeMs: 612,
    lastCheckedAt: '2026-04-30T10:40:00Z',
    lastIncidentAt: '2026-04-30T08:12:00Z',
    summary: 'Homepage latency watch with soft alert threshold for slow responses.',
    expected: { status: 200, bodyContains: 'Pricing' },
  },
  {
    id: 'checkout-flow',
    name: 'Checkout Browser Flow',
    type: 'browser',
    status: 'down',
    url: 'https://shop.example.com',
    intervalSeconds: 300,
    location: 'us-east-1',
    groupId: 'grp-core',
    tags: ['e2e', 'payments'],
    uptime24h: 97.8,
    responseTimeMs: null,
    lastCheckedAt: '2026-04-30T10:38:00Z',
    lastIncidentAt: '2026-04-30T10:16:00Z',
    summary: 'Critical checkout flow run via Playwright scenario.',
    steps: [
      { id: 'step-1', action: 'goto', label: 'Open storefront', url: 'https://shop.example.com' },
      { id: 'step-2', action: 'click', label: 'Open cart', selector: '[data-test="cart-button"]' },
      { id: 'step-3', action: 'type', label: 'Enter email', selector: '#email', value: 'buyer@example.com' },
      { id: 'step-4', action: 'assert_text', label: 'Confirm payment screen', expectedText: 'Payment details' },
    ],
  },
  {
    id: 'staging-login',
    name: 'Staging Login',
    type: 'browser',
    status: 'paused',
    url: 'https://staging.example.com/login',
    intervalSeconds: 600,
    location: 'local-docker',
    groupId: 'grp-core',
    tags: ['staging'],
    uptime24h: 100,
    responseTimeMs: null,
    lastCheckedAt: '2026-04-29T22:00:00Z',
    summary: 'Paused during environment migration.',
    steps: [
      { id: 'step-a', action: 'goto', label: 'Open login page', url: 'https://staging.example.com/login' },
      { id: 'step-b', action: 'assert_text', label: 'Validate title', expectedText: 'Sign in' },
    ],
  },
];

const checks: CheckResult[] = [
  {
    id: 'chk-1',
    monitorId: 'api-health',
    timestamp: '2026-04-30T10:43:00Z',
    status: 'up',
    responseTimeMs: 124,
    location: 'eu-central-1',
    logLines: ['GET /health', 'Status 200', 'Body contains "ok"'],
  },
  {
    id: 'chk-2',
    monitorId: 'api-health',
    timestamp: '2026-04-30T10:42:00Z',
    status: 'up',
    responseTimeMs: 129,
    location: 'eu-central-1',
    logLines: ['GET /health', 'Status 200', 'Response 129ms'],
  },
  {
    id: 'chk-3',
    monitorId: 'marketing-home',
    timestamp: '2026-04-30T10:40:00Z',
    status: 'degraded',
    responseTimeMs: 612,
    location: 'eu-west-1',
    logLines: ['GET /', 'TTFB high', 'Threshold exceeded by 212ms'],
  },
  {
    id: 'chk-4',
    monitorId: 'marketing-home',
    timestamp: '2026-04-30T10:38:00Z',
    status: 'up',
    responseTimeMs: 341,
    location: 'eu-west-1',
    logLines: ['GET /', 'Status 200', 'Content includes Pricing'],
  },
  {
    id: 'chk-5',
    monitorId: 'checkout-flow',
    timestamp: '2026-04-30T10:38:00Z',
    status: 'down',
    responseTimeMs: null,
    error: 'Assertion failed: "Payment details" not found within 30s',
    location: 'us-east-1',
    logLines: [
      'goto https://shop.example.com',
      'click [data-test="cart-button"]',
      'type #email',
      'assert_text Payment details',
    ],
  },
  {
    id: 'chk-6',
    monitorId: 'checkout-flow',
    timestamp: '2026-04-30T10:33:00Z',
    status: 'down',
    responseTimeMs: null,
    error: 'Navigation timeout after 30s',
    location: 'us-east-1',
    logLines: ['goto https://shop.example.com', 'Navigation timeout 30000ms'],
  },
  {
    id: 'chk-7',
    monitorId: 'checkout-flow',
    timestamp: '2026-04-30T10:28:00Z',
    status: 'up',
    responseTimeMs: 1820,
    location: 'us-east-1',
    logLines: ['Scenario completed', '4 steps passed'],
  },
  {
    id: 'chk-8',
    monitorId: 'staging-login',
    timestamp: '2026-04-29T22:00:00Z',
    status: 'paused',
    responseTimeMs: null,
    location: 'local-docker',
    logLines: ['Scheduler paused by operator'],
  },
];

const incidents: Incident[] = [
  {
    id: 'inc-1',
    monitorId: 'checkout-flow',
    title: 'Checkout scenario failing on payment step',
    severity: 'critical',
    startedAt: '2026-04-30T10:16:00Z',
    impact: 'Users may be unable to reach the payment screen.',
  },
  {
    id: 'inc-2',
    monitorId: 'marketing-home',
    title: 'Homepage latency spike in EU',
    severity: 'warning',
    startedAt: '2026-04-30T08:12:00Z',
    resolvedAt: '2026-04-30T09:05:00Z',
    impact: 'Slow page loads impacting campaign traffic.',
  },
];

const responseSeries: Record<string, ResponsePoint[]> = {
  'api-health': [
    { label: '00:00', responseTimeMs: 128, status: 'up' },
    { label: '04:00', responseTimeMs: 132, status: 'up' },
    { label: '08:00', responseTimeMs: 121, status: 'up' },
    { label: '12:00', responseTimeMs: 118, status: 'up' },
    { label: '16:00', responseTimeMs: 136, status: 'up' },
    { label: '20:00', responseTimeMs: 124, status: 'up' },
  ],
  'marketing-home': [
    { label: '00:00', responseTimeMs: 301, status: 'up' },
    { label: '04:00', responseTimeMs: 332, status: 'up' },
    { label: '08:00', responseTimeMs: 588, status: 'degraded' },
    { label: '12:00', responseTimeMs: 612, status: 'degraded' },
    { label: '16:00', responseTimeMs: 404, status: 'up' },
    { label: '20:00', responseTimeMs: 355, status: 'up' },
  ],
  'checkout-flow': [
    { label: '00:00', responseTimeMs: 1720, status: 'up' },
    { label: '04:00', responseTimeMs: 1810, status: 'up' },
    { label: '08:00', responseTimeMs: 1960, status: 'up' },
    { label: '12:00', responseTimeMs: 2000, status: 'down' },
    { label: '16:00', responseTimeMs: 2100, status: 'down' },
    { label: '20:00', responseTimeMs: 2075, status: 'down' },
  ],
  'staging-login': [],
};

const configVersions: ConfigVersion[] = [
  {
    id: 'cfg-12',
    version: 12,
    createdAt: '2026-04-30T10:11:00Z',
    author: 'Julia Dovzhenko',
    summary: 'Added browser checkout assertions and updated homepage latency threshold.',
    content: `version: 1

monitors:
  - id: api-health
    type: http
    url: https://api.example.com/health
    interval: 60
    expected:
      status: 200
      body_contains: "ok"

  - id: marketing-home
    type: http
    url: https://example.com
    interval: 120
    expected:
      status: 200
      body_contains: "Pricing"

  - id: checkout-flow
    type: browser
    interval: 300
    steps:
      - action: goto
        url: https://shop.example.com
      - action: click
        selector: "[data-test='cart-button']"
      - action: type
        selector: "#email"
        value: "buyer@example.com"
      - action: assert_text
        text: "Payment details"
`,
  },
  {
    id: 'cfg-11',
    version: 11,
    createdAt: '2026-04-29T18:42:00Z',
    author: 'Maksim Orlov',
    summary: 'Initial import from self-hosted YAML.',
    content: `version: 1

monitors:
  - id: api-health
    type: http
    url: https://api.example.com/health
    interval: 60
    expected:
      status: 200
      body_contains: "ok"
`,
  },
];

const telegramIntegration: TelegramIntegration = {
  connected: true,
  botName: '@uplynx_alerts_bot',
  chatId: '-10014578291',
  alerts: ['down', 'degraded', 'recovered'],
  lastTestAt: '2026-04-30T09:48:00Z',
};

export function getCurrentUser() {
  return currentUser;
}

export function getGroups() {
  return groups;
}

export function getActiveGroup() {
  return groups.find((group) => group.id === currentUser.activeGroupId) ?? groups[0];
}

export function getMonitors() {
  return monitors;
}

export function getMonitorById(id: string) {
  return monitors.find((monitor) => monitor.id === id);
}

export function getChecksForMonitor(monitorId: string) {
  return checks.filter((check) => check.monitorId === monitorId);
}

export function getIncidentsForMonitor(monitorId: string) {
  return incidents.filter((incident) => incident.monitorId === monitorId);
}

export function getConfigVersions() {
  return configVersions;
}

export function getTelegramIntegration() {
  return telegramIntegration;
}

export function getResponseSeries(monitorId: string) {
  return responseSeries[monitorId] ?? [];
}

export function getMonitorHealthTimeline(monitorId: string) {
  return monitorHealthTimeline[monitorId] ?? [];
}

export function getDashboardSummary() {
  const total = monitors.length;
  const down = monitors.filter((monitor) => monitor.status === 'down').length;
  const degraded = monitors.filter((monitor) => monitor.status === 'degraded').length;
  const paused = monitors.filter((monitor) => monitor.status === 'paused').length;
  const averageUptime = Number(
    (monitors.reduce((sum, monitor) => sum + monitor.uptime24h, 0) / total).toFixed(2)
  );

  return {
    total,
    down,
    degraded,
    paused,
    averageUptime,
  };
}

export function getResponseSummary(monitorId: string) {
  const entries = getChecksForMonitor(monitorId).filter(
    (check) => typeof check.responseTimeMs === 'number'
  );

  if (entries.length === 0) {
    return { averageMs: null, slowestMs: null };
  }

  const total = entries.reduce((sum, check) => sum + (check.responseTimeMs ?? 0), 0);
  const slowest = Math.max(...entries.map((check) => check.responseTimeMs ?? 0));

  return {
    averageMs: Math.round(total / entries.length),
    slowestMs: slowest,
  };
}

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
    default:
      return status;
  }
}

export function getStatusTone(status: MonitorStatus) {
  switch (status) {
    case 'up':
      return 'emerald';
    case 'down':
      return 'rose';
    case 'paused':
      return 'slate';
    case 'degraded':
      return 'amber';
    default:
      return 'slate';
  }
}

export function getSeverityLabel(severity: AlertSeverity) {
  switch (severity) {
    case 'critical':
      return 'Critical';
    case 'warning':
      return 'Warning';
    case 'info':
      return 'Info';
    default:
      return severity;
  }
}
