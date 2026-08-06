import { useEffect, useMemo, useState } from 'react';
import { Navigate, useNavigate, useParams } from 'react-router';
import {
  Activity,
  ArrowRight,
  Clock3,
  FileText,
  Globe,
  Pencil,
  RefreshCw,
  ServerCog,
  Siren,
  Trash2,
  Zap,
} from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/Card';
import { StatusBadge } from '../components/StatusBadge';
import {
  ApiError,
  getHistory,
  getMonitor,
  getMonitorIncidents,
  deleteMonitor,
  runCheckNow,
  type CheckResult,
  type Incident,
  type Monitor,
} from '../api';
import { cn } from '../utils/cn';
import { monitorStatusTexts, plural, useTexts } from '../i18n';
import { formatDuration, formatRelativeTime } from '../utils/time';
import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';

const ranges = ['1h', '24h', '7d', '30d'] as const;

export default function MonitorDetails() {
  const statusLabels = useTexts(monitorStatusTexts);
  const t = useTexts({
    ru: {
      loadErrorFallback: 'Не удалось загрузить монитор',
      queueErrorFallback: 'Не удалось поставить проверку в очередь',
      loadingMonitor: 'Загрузка монитора...',
      loadErrorTitle: 'Не удалось загрузить монитор',
      checkQueued: 'Проверка в очереди',
      checkNow: 'Проверить сейчас',
      edit: 'Редактировать',
      remove: 'Удалить',
      confirmRemove: (name: string) =>
        `Удалить монитор «${name}»? Он исчезнет из дашборда и перестанет проверяться. История сохранится, но вернуть монитор из интерфейса будет нельзя.`,
      removeError: 'Не удалось удалить монитор.',
      viewHistory: 'Открыть историю',
      metricStatus: 'Статус',
      metricStatusHint: 'Текущее состояние монитора',
      metricUptime: 'Аптайм',
      metricUptimeHint: (range: string) => `Доля успешных проверок за последние ${range}`,
      metricAvgResponse: 'Среднее время ответа',
      noData: 'Нет данных',
      metricAvgResponseHint: (range: string) => `По проверкам за последние ${range}`,
      metricChecks: 'Проверки',
      metricChecksHint: (range: string) => `Выполнено за последние ${range}`,
      metricInterval: 'Интервал',
      metricIntervalHint: 'Периодичность планировщика',
      unitSeconds: 'с',
      unitMinutes: 'мин',
      unitMs: 'мс',
      rangeLabel: (range: (typeof ranges)[number]) =>
        ({ '1h': '1 ч', '24h': '24 ч', '7d': '7 дн', '30d': '30 дн' })[range],
      chartTitle: 'Динамика времени ответа',
      emptyChartTitle: 'В этом диапазоне пока нет проверок.',
      emptyChartPending: 'Монитор ожидает первую запланированную проверку.',
      emptyChartWiden: 'Попробуйте более широкий диапазон, чтобы увидеть более ранние результаты.',
      configSummary: 'Сводка настроек',
      httpExpectations: 'Ожидания HTTP',
      expectedStatus: 'Статус',
      expectedBodyContains: 'Тело содержит',
      expectedResponseTime: (ms: number) => `Порог времени ответа: ${ms} мс`,
      antiFlapping: 'Защита от дребезга',
      confirmations: (n: number) =>
        `Подтверждения: ${n} ${plural(n, ['последовательная проверка', 'последовательные проверки', 'последовательных проверок'])} до смены статуса`,
      reAlerts: 'Повторные оповещения',
      reAlertsText: (min: number) => `Повторять оповещения каждые ${min} мин, пока монитор недоступен`,
      browserScenario: 'Браузерный сценарий',
      sslCertificate: 'SSL-сертификат',
      sslExpired: 'Истёк',
      sslExpiresIn: (days: number) => `Истекает через ${days} ${plural(days, ['день', 'дня', 'дней'])}`,
      lastCheck: 'Последняя проверка',
      responseTime: (ms: number) => `Время ответа: ${ms} мс`,
      noResponseTime: 'Время ответа не зафиксировано',
      noChecksYet: 'Проверок пока не было.',
      incidents: 'Инциденты',
      noIncidents: 'Инцидентов не зафиксировано.',
      incidentStarted: (relative: string) => `Начался ${relative}`,
      ongoing: 'Продолжается',
      recentChecks: 'Последние проверки',
      noChecksInRange: 'В этом диапазоне нет проверок. Новые результаты появятся после запуска планировщика.',
      noResponse: 'Нет ответа',
      failedAtStep: (index: number) => `Ошибка на шаге ${index}:`,
    },
    en: {
      loadErrorFallback: 'Unable to load monitor',
      queueErrorFallback: 'Unable to queue check',
      loadingMonitor: 'Loading monitor...',
      loadErrorTitle: 'Unable to load monitor',
      checkQueued: 'Check queued',
      checkNow: 'Check now',
      edit: 'Edit',
      remove: 'Delete',
      confirmRemove: (name: string) =>
        `Delete monitor "${name}"? It disappears from the dashboard and stops being checked. History is kept, but the monitor cannot be restored from the UI.`,
      removeError: 'Unable to delete the monitor.',
      viewHistory: 'View history',
      metricStatus: 'Status',
      metricStatusHint: 'Current monitor state',
      metricUptime: 'Uptime',
      metricUptimeHint: (range: string) => `Share of successful checks in the last ${range}`,
      metricAvgResponse: 'Average response',
      noData: 'No data',
      metricAvgResponseHint: (range: string) => `From checks in the last ${range}`,
      metricChecks: 'Checks',
      metricChecksHint: (range: string) => `Completed in the last ${range}`,
      metricInterval: 'Interval',
      metricIntervalHint: 'Scheduler cadence',
      unitSeconds: 's',
      unitMinutes: 'min',
      unitMs: 'ms',
      rangeLabel: (range: (typeof ranges)[number]) => range as string,
      chartTitle: 'Response pattern',
      emptyChartTitle: 'No checks in this range yet.',
      emptyChartPending: 'This monitor is pending its first scheduled check.',
      emptyChartWiden: 'Try a wider time range to see earlier results.',
      configSummary: 'Config summary',
      httpExpectations: 'HTTP expectations',
      expectedStatus: 'Status',
      expectedBodyContains: 'Body contains',
      expectedResponseTime: (ms: number) => `Response time threshold: ${ms} ms`,
      antiFlapping: 'Anti-flapping',
      confirmations: (n: number) => `Confirmations: ${n} consecutive checks before a status change`,
      reAlerts: 'Re-alerts',
      reAlertsText: (min: number) => `Repeat alerts every ${min} min while the monitor is down`,
      browserScenario: 'Browser scenario',
      sslCertificate: 'SSL certificate',
      sslExpired: 'Expired',
      sslExpiresIn: (days: number) => `Expires in ${days} days`,
      lastCheck: 'Last check',
      responseTime: (ms: number) => `Response time: ${ms} ms`,
      noResponseTime: 'No response time recorded',
      noChecksYet: 'No checks recorded yet.',
      incidents: 'Incidents',
      noIncidents: 'No incidents recorded.',
      incidentStarted: (relative: string) => `Started ${relative}`,
      ongoing: 'Ongoing',
      recentChecks: 'Recent checks',
      noChecksInRange: 'No checks recorded in this range. New results appear here after the scheduler runs.',
      noResponse: 'No response',
      failedAtStep: (index: number) => `Failed at step ${index}:`,
    },
  });
  const { id = '' } = useParams();
  const navigate = useNavigate();
  const [monitor, setMonitor] = useState<Monitor | null>(null);
  const [checks, setChecks] = useState<CheckResult[]>([]);
  const [incidents, setIncidents] = useState<Incident[]>([]);
  const [range, setRange] = useState<(typeof ranges)[number]>('24h');
  const [loading, setLoading] = useState(true);
  const [notFound, setNotFound] = useState(false);
  const [error, setError] = useState('');
  const [refreshKey, setRefreshKey] = useState(0);
  const [checkNowState, setCheckNowState] = useState<'idle' | 'queueing' | 'queued'>('idle');
  const [isDeleting, setIsDeleting] = useState(false);

  useEffect(() => {
    let ignore = false;

    setLoading(true);

    Promise.all([getMonitor(id), getHistory({ monitorId: id, range }), getMonitorIncidents(id)])
      .then(([monitorData, history, incidentsData]) => {
        if (!ignore) {
          setMonitor(monitorData);
          setChecks(history);
          setIncidents(incidentsData);
          setError('');
        }
      })
      .catch((error) => {
        if (!ignore) {
          if (error instanceof ApiError && error.status === 404) {
            setNotFound(true);
          } else {
            setError(error instanceof Error ? error.message : t.loadErrorFallback);
          }
        }
      })
      .finally(() => {
        if (!ignore) {
          setLoading(false);
        }
      });

    return () => {
      ignore = true;
    };
  }, [id, range, refreshKey]);

  const handleDelete = async () => {
    if (!monitor || !window.confirm(t.confirmRemove(monitor.name))) {
      return;
    }

    setIsDeleting(true);
    try {
      await deleteMonitor(id);
      navigate('/');
    } catch (error) {
      setError(error instanceof Error ? error.message : t.removeError);
      setIsDeleting(false);
    }
  };

  const handleCheckNow = async () => {
    setCheckNowState('queueing');
    try {
      await runCheckNow(id);
      setCheckNowState('queued');
      // проверка асинхронная: результат появится после того, как воркер её выполнит
      setTimeout(() => {
        setRefreshKey((key) => key + 1);
        setCheckNowState('idle');
      }, 4000);
    } catch (error) {
      setError(error instanceof Error ? error.message : t.queueErrorFallback);
      setCheckNowState('idle');
    }
  };

  const chartData = useMemo(
    () =>
      [...checks]
        .reverse()
        .map((check) => ({
          label: new Date(check.timestamp).toLocaleString(undefined, {
            month: range === '7d' || range === '30d' ? 'short' : undefined,
            day: range === '7d' || range === '30d' ? 'numeric' : undefined,
            hour: '2-digit',
            minute: '2-digit',
          }),
          responseTimeMs: check.response_time_ms,
        })),
    [checks, range]
  );

  const averageMs = useMemo(() => {
    const entries = checks.filter((check) => typeof check.response_time_ms === 'number');

    if (entries.length === 0) {
      return null;
    }

    return Math.round(entries.reduce((sum, check) => sum + (check.response_time_ms ?? 0), 0) / entries.length);
  }, [checks]);

  const uptimePct = useMemo(() => {
    if (checks.length === 0) {
      return null;
    }

    const up = checks.filter((check) => check.status === 'up').length;

    return Math.round((up / checks.length) * 1000) / 10;
  }, [checks]);

  if (notFound) {
    return <Navigate to="/" replace />;
  }

  if (loading && !monitor) {
    return (
      <div className="rounded-lg border border-dashed border-border bg-secondary p-12 text-center">
        <p className="text-lg font-semibold text-foreground">{t.loadingMonitor}</p>
      </div>
    );
  }

  if (error && !monitor) {
    return (
      <div className="rounded-lg bg-destructive/10 p-12 text-center">
        <p className="text-lg font-semibold text-destructive">{t.loadErrorTitle}</p>
        <p className="mt-2 text-sm text-destructive">{error}</p>
      </div>
    );
  }

  if (!monitor) {
    return <Navigate to="/" replace />;
  }

  const expected = monitor.config.expected;
  const steps = monitor.config.steps ?? [];
  const lastCheck = checks[0];

  return (
    <div className="space-y-6">
      <section className="rounded-lg bg-card p-6 shadow-card">
        <div className="flex flex-col gap-6 xl:flex-row xl:items-start xl:justify-between">
          <div className="space-y-4">
            <div className="flex flex-wrap items-center gap-3">
              <StatusBadge status={monitor.status} />
              <span className="rounded-lg bg-secondary px-3 py-1 text-xs font-semibold uppercase text-muted-foreground">
                {monitor.type}
              </span>
            </div>
            <div>
              <h1 className="text-2xl font-semibold leading-8 text-foreground">{monitor.name}</h1>
              {monitor.url && (
                <p className="mt-2 flex items-center gap-2 text-sm text-muted-foreground">
                  <Globe className="h-4 w-4 text-placeholder" />
                  {monitor.url}
                </p>
              )}
            </div>
          </div>

          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              onClick={handleCheckNow}
              disabled={checkNowState !== 'idle' || !monitor.enabled || monitor.in_maintenance}
              className="inline-flex items-center gap-2 rounded-lg bg-primary px-3 py-1.5 text-sm font-medium text-primary-foreground transition-colors hover:bg-primary-hover disabled:cursor-not-allowed disabled:opacity-60"
            >
              <RefreshCw className={cn('h-4 w-4', checkNowState === 'queueing' && 'animate-spin')} />
              {checkNowState === 'queued' ? t.checkQueued : t.checkNow}
            </button>
            <button
              type="button"
              onClick={() => navigate(`/monitors/${monitor.id}/history`)}
              className="inline-flex items-center gap-2 rounded-lg border border-secondary bg-card px-3 py-1.5 text-sm font-medium text-primary transition-colors hover:border-border"
            >
              {t.viewHistory}
              <ArrowRight className="h-4 w-4" />
            </button>
            <button
              type="button"
              onClick={() => navigate(`/monitors/${monitor.id}/edit`)}
              className="inline-flex items-center gap-2 rounded-lg border border-secondary bg-card px-3 py-1.5 text-sm font-medium text-primary transition-colors hover:border-border"
            >
              <Pencil className="h-4 w-4" />
              {t.edit}
            </button>
            <button
              type="button"
              onClick={handleDelete}
              disabled={isDeleting}
              className="inline-flex items-center gap-2 rounded-lg border border-secondary bg-card px-3 py-1.5 text-sm font-medium text-destructive transition-colors hover:border-destructive disabled:cursor-not-allowed disabled:opacity-60"
            >
              <Trash2 className="h-4 w-4" />
              {t.remove}
            </button>
          </div>
        </div>
      </section>

      {error && (
        <div className="rounded-lg bg-destructive/10 p-4 text-sm text-destructive">{error}</div>
      )}

      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-5">
        <MetricCard label={t.metricStatus} value={statusLabels[monitor.status]} hint={t.metricStatusHint} icon={Zap} />
        <MetricCard
          label={t.metricUptime}
          value={uptimePct !== null ? `${uptimePct}%` : '—'}
          hint={t.metricUptimeHint(t.rangeLabel(range))}
          icon={Activity}
        />
        <MetricCard
          label={t.metricAvgResponse}
          value={averageMs !== null ? `${averageMs} ${t.unitMs}` : t.noData}
          hint={t.metricAvgResponseHint(t.rangeLabel(range))}
          icon={Clock3}
        />
        <MetricCard label={t.metricChecks} value={String(checks.length)} hint={t.metricChecksHint(t.rangeLabel(range))} icon={FileText} />
        <MetricCard
          label={t.metricInterval}
          value={monitor.interval < 60 ? `${monitor.interval} ${t.unitSeconds}` : `${Math.round(monitor.interval / 60)} ${t.unitMinutes}`}
          hint={t.metricIntervalHint}
          icon={ServerCog}
        />
      </div>

      <div className="grid gap-6 xl:grid-cols-[1.2fr_0.8fr]">
        <Card>
          <CardHeader>
            <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
              <CardTitle>{t.chartTitle}</CardTitle>
              <div className="flex flex-wrap gap-2">
                {ranges.map((item) => (
                  <button
                    key={item}
                    type="button"
                    onClick={() => setRange(item)}
                    className={cn(
                      'rounded-lg px-3 py-1.5 text-[13px] leading-5 transition-colors',
                      range === item
                        ? 'bg-accent font-semibold text-primary'
                        : 'bg-secondary text-foreground hover:text-primary'
                    )}
                  >
                    {t.rangeLabel(item)}
                  </button>
                ))}
              </div>
            </div>
          </CardHeader>
          <CardContent>
            {chartData.length === 0 ? (
              <div className="rounded-lg border border-dashed border-border bg-secondary p-10 text-center text-sm text-placeholder">
                <p className="font-semibold text-muted-foreground">{t.emptyChartTitle}</p>
                <p className="mt-2">
                  {monitor.status === 'pending'
                    ? t.emptyChartPending
                    : t.emptyChartWiden}
                </p>
              </div>
            ) : (
              <div className="h-72">
                <ResponsiveContainer width="100%" height="100%">
                  <AreaChart data={chartData} margin={{ top: 16, right: 12, left: -20, bottom: 0 }}>
                    <defs>
                      <linearGradient id="monitor-response" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="0%" stopColor="#00AC86" stopOpacity={0.25} />
                        <stop offset="100%" stopColor="#00AC86" stopOpacity={0.02} />
                      </linearGradient>
                    </defs>
                    <CartesianGrid vertical={false} stroke="#E7E7E7" strokeDasharray="3 3" />
                    <XAxis dataKey="label" axisLine={false} tickLine={false} tick={{ fill: '#969FA8', fontSize: 12 }} />
                    <YAxis axisLine={false} tickLine={false} tick={{ fill: '#969FA8', fontSize: 12 }} />
                    <Tooltip
                      cursor={{ stroke: '#E6F7F3', strokeWidth: 1 }}
                      contentStyle={{ borderRadius: 8, border: '1px solid #E7E7E7', boxShadow: '0px 4px 24px 0px rgba(0, 0, 0, 0.06)' }}
                    />
                    <Area
                      type="monotone"
                      dataKey="responseTimeMs"
                      stroke="#00AC86"
                      strokeWidth={2}
                      fill="url(#monitor-response)"
                    />
                  </AreaChart>
                </ResponsiveContainer>
              </div>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>{t.configSummary}</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4 text-sm text-muted-foreground">
            {expected && (
              <div className="rounded-lg bg-secondary p-4">
                <p className="font-semibold text-foreground">{t.httpExpectations}</p>
                {expected.status !== undefined && <p className="mt-2">{t.expectedStatus}: {expected.status}</p>}
                {expected.body_contains !== undefined && <p>{t.expectedBodyContains}: {expected.body_contains}</p>}
                {expected.response_time_ms !== undefined && <p>{t.expectedResponseTime(expected.response_time_ms)}</p>}
              </div>
            )}

            {(monitor.confirmations ?? 1) > 1 && (
              <div className="rounded-lg bg-secondary p-4">
                <p className="font-semibold text-foreground">{t.antiFlapping}</p>
                <p className="mt-2">{t.confirmations(monitor.confirmations ?? 1)}</p>
              </div>
            )}

            {(monitor.config.renotify_interval_minutes ?? 0) > 0 && (
              <div className="rounded-lg bg-secondary p-4">
                <p className="font-semibold text-foreground">{t.reAlerts}</p>
                <p className="mt-2">
                  {t.reAlertsText(monitor.config.renotify_interval_minutes ?? 0)}
                </p>
              </div>
            )}

            {steps.length > 0 && (
              <div className="rounded-lg bg-secondary p-4">
                <p className="font-semibold text-foreground">{t.browserScenario}</p>
                <div className="mt-3 space-y-3">
                  {steps.map((step, index) => (
                    <div key={index} className="flex gap-3">
                      <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-card text-xs font-semibold text-muted-foreground">
                        {index + 1}
                      </div>
                      <div>
                        <p className="font-medium text-foreground">{step.action}</p>
                        <p className="text-xs text-placeholder">
                          {step.url ?? step.selector ?? step.text ?? step.value ?? ''}
                        </p>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {monitor.ssl_expires_at && (
              <div className="rounded-lg bg-secondary p-4">
                <p className="font-semibold text-foreground">{t.sslCertificate}</p>
                <p
                  className={cn(
                    'mt-2',
                    (monitor.ssl_days_left ?? 0) <= 7
                      ? 'font-semibold text-status-down'
                      : (monitor.ssl_days_left ?? 0) <= 14
                        ? 'font-semibold text-status-degraded'
                        : undefined
                  )}
                >
                  {monitor.ssl_days_left !== null && monitor.ssl_days_left !== undefined && monitor.ssl_days_left <= 0
                    ? t.sslExpired
                    : t.sslExpiresIn(monitor.ssl_days_left ?? 0)}{' '}
                  ({new Date(monitor.ssl_expires_at).toLocaleDateString()})
                </p>
              </div>
            )}

            <div className="rounded-lg bg-secondary p-4">
              <p className="font-semibold text-foreground">{t.lastCheck}</p>
              {lastCheck ? (
                <div className="mt-3 space-y-2 text-xs text-muted-foreground">
                  <div className="flex items-center gap-2">
                    <StatusBadge status={lastCheck.status} />
                    <span>{new Date(lastCheck.timestamp).toLocaleString()}</span>
                  </div>
                  <p>
                    {lastCheck.response_time_ms !== null
                      ? t.responseTime(lastCheck.response_time_ms)
                      : t.noResponseTime}
                  </p>
                  {lastCheck.error && <p className="font-medium text-destructive">{lastCheck.error}</p>}
                </div>
              ) : (
                <p className="mt-3 text-xs text-placeholder">{t.noChecksYet}</p>
              )}
            </div>
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Siren className="h-5 w-5 text-primary" />
            {t.incidents}
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          {incidents.length === 0 ? (
            <div className="rounded-lg border border-dashed border-border bg-secondary p-8 text-center text-sm text-placeholder">
              {t.noIncidents}
            </div>
          ) : (
            incidents.map((incident) => (
              <div key={incident.id} className="rounded-lg border border-border p-4">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div className="flex flex-wrap items-center gap-3">
                    <StatusBadge status={incident.severity} />
                    <p className="text-sm text-muted-foreground">{t.incidentStarted(formatRelativeTime(incident.started_at))}</p>
                  </div>
                  {incident.status === 'open' ? (
                    <span className="inline-flex items-center rounded-lg bg-status-down/10 px-2.5 py-1 text-xs font-semibold text-status-down">
                      {t.ongoing}
                    </span>
                  ) : (
                    <p className="text-sm font-semibold text-foreground">{formatDuration(incident.duration_seconds)}</p>
                  )}
                </div>
                {incident.trigger_error && (
                  <p className="mt-2 truncate text-xs text-placeholder">{incident.trigger_error}</p>
                )}
              </div>
            ))
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <FileText className="h-5 w-5 text-primary" />
            {t.recentChecks}
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          {checks.length === 0 ? (
            <div className="rounded-lg border border-dashed border-border bg-secondary p-8 text-center text-sm text-placeholder">
              {t.noChecksInRange}
            </div>
          ) : (
            checks.slice(0, 10).map((check) => (
              <div key={check.id} className="rounded-lg border border-border p-4">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div className="flex items-center gap-3">
                    <StatusBadge status={check.status} />
                    <p className="text-sm font-medium text-foreground">{new Date(check.timestamp).toLocaleString()}</p>
                  </div>
                  <p className="text-sm text-muted-foreground">
                    {check.response_time_ms !== null ? `${check.response_time_ms} ${t.unitMs}` : check.error ?? t.noResponse}
                  </p>
                </div>
                {check.error && <p className="mt-3 text-xs leading-5 text-destructive">{check.error}</p>}
                {check.details.failed_step && (
                  <p className="mt-2 text-xs text-muted-foreground">
                    {t.failedAtStep(check.details.failed_step.index)} {check.details.failed_step.action}{' '}
                    {check.details.failed_step.selector ?? check.details.failed_step.url ?? check.details.failed_step.contains ?? ''}
                  </p>
                )}
              </div>
            ))
          )}
        </CardContent>
      </Card>
    </div>
  );
}

function MetricCard({
  label,
  value,
  hint,
  icon: Icon,
}: {
  label: string;
  value: string;
  hint: string;
  icon: typeof Zap;
}) {
  return (
    <Card>
      <CardContent className="space-y-3 p-5">
        <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-accent text-primary">
          <Icon className="h-5 w-5" />
        </div>
        <div>
          <p className="text-sm text-muted-foreground">{label}</p>
          <p className="mt-1 text-2xl font-semibold leading-8 text-foreground">{value}</p>
          <p className="mt-2 text-xs text-placeholder">{hint}</p>
        </div>
      </CardContent>
    </Card>
  );
}
