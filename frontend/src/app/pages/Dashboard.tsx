import { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router';
import {
  AlertTriangle,
  ChevronRight,
  Clock3,
  Plus,
  Search,
  Siren,
  SlidersHorizontal,
  Waves,
  Workflow,
} from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/Card';
import { Input } from '../components/ui/Input';
import { StatusBadge } from '../components/StatusBadge';
import {
  getMonitorsUptime,
  listMonitors,
  type Monitor,
  type MonitorStatus,
  type MonitorType,
  type MonitorUptime,
} from '../api';
import { useMeta } from '../meta-context';
import { plural, useTexts } from '../i18n';
import { cn } from '../utils/cn';
import { formatRelativeTime } from '../utils/time';

export default function Dashboard() {
  const t = useTexts({
    ru: {
      overview: 'Оперативная сводка',
      heroTitle: 'Состояние парка мониторов',
      heroText:
        'Каждая карточка ниже отражает живое состояние из пайплайна проверок. Откройте сервис, чтобы посмотреть историю откликов, или перейдите сразу в конфиг, чтобы настроить, что именно мониторится.',
      openConfig: 'Открыть конфиг',
      newMonitor: 'Новый монитор',
      fleetHealth: 'Здоровье парка',
      noMonitorsYet: 'Мониторов пока нет',
      avgUptimeHint: 'Средний аптайм за последние 24 часа',
      downMonitors: 'Недоступные мониторы',
      downHint: 'Требуют немедленных действий',
      degraded: 'Деградация',
      degradedHint: 'Медленные или нестабильные проверки',
      paused: 'На паузе',
      pausedHint: 'Временно исключены из проверок',
      serviceRoster: 'Список сервисов',
      monitorCount: (count: number, limit: number) =>
        `${count} / ${limit} ${plural(limit, ['монитор', 'монитора', 'мониторов'])}`,
      rosterSubtitle: 'Поиск и фильтрация отслеживаемых сервисов.',
      searchPlaceholder: 'Поиск по имени или URL...',
      filters: 'Фильтры',
      filterAll: 'Все',
      filterAnyState: 'Любой статус',
      filterHealthy: 'Работает',
      filterDown: 'Недоступен',
      filterPending: 'Ожидание',
      loadingMonitors: 'Загрузка мониторов...',
      loadError: 'Не удалось загрузить мониторы',
      emptyCreateFirst: 'Создайте первый монитор или загрузите конфиг, чтобы начать.',
      noMatch: 'Нет мониторов, подходящих под фильтры',
      noMatchHint: 'Попробуйте сбросить фильтр или изменить поисковый запрос.',
      maintenance: 'Обслуживание',
      ssl: (days: number) => (days <= 0 ? 'SSL истёк' : `SSL ${days} дн`),
      statUptime: 'Аптайм 24 ч',
      statLastCheck: 'Последняя проверка',
      statResponse: 'Отклик',
      statInterval: 'Интервал',
      checksEnabled: 'Плановые проверки включены',
      checksPaused: 'Проверки на паузе',
      openService: 'Открыть сервис',
      formatInterval: (seconds: number) => (seconds < 60 ? `${seconds} с` : `${Math.round(seconds / 60)} мин`),
      formatResponse: (ms: number | null | undefined) => (typeof ms === 'number' ? `${ms} мс` : '—'),
    },
    en: {
      overview: 'Operational overview',
      heroTitle: 'Fleet status at a glance',
      heroText:
        'Every card below reflects the live state reported by the checks pipeline. Open a service to see its response history, or jump straight into the config to change what is monitored.',
      openConfig: 'Open config',
      newMonitor: 'New monitor',
      fleetHealth: 'Fleet health',
      noMonitorsYet: 'No monitors yet',
      avgUptimeHint: 'Average uptime over the last 24h',
      downMonitors: 'Down monitors',
      downHint: 'Require immediate action',
      degraded: 'Degraded',
      degradedHint: 'Slow or unstable checks',
      paused: 'Paused',
      pausedHint: 'Temporarily excluded from checks',
      serviceRoster: 'Service roster',
      monitorCount: (count: number, limit: number) => `${count} / ${limit} monitors`,
      rosterSubtitle: 'Search and filter the monitored services.',
      searchPlaceholder: 'Search by name or URL...',
      filters: 'Filters',
      filterAll: 'All',
      filterAnyState: 'Any state',
      filterHealthy: 'Healthy',
      filterDown: 'Down',
      filterPending: 'Pending',
      loadingMonitors: 'Loading monitors...',
      loadError: 'Unable to load monitors',
      emptyCreateFirst: 'Create your first monitor or upload a config to get started.',
      noMatch: 'No monitors match these filters',
      noMatchHint: 'Try resetting a filter or adjusting the search query.',
      maintenance: 'Maintenance',
      ssl: (days: number) => (days <= 0 ? 'SSL expired' : `SSL ${days}d`),
      statUptime: 'Uptime 24h',
      statLastCheck: 'Last check',
      statResponse: 'Response',
      statInterval: 'Interval',
      checksEnabled: 'Scheduled checks enabled',
      checksPaused: 'Checks paused',
      openService: 'Open service',
      formatInterval: (seconds: number) => (seconds < 60 ? `${seconds} s` : `${Math.round(seconds / 60)} min`),
      formatResponse: (ms: number | null | undefined) => (typeof ms === 'number' ? `${ms} ms` : '—'),
    },
  });

  const typeFilters: Array<{ value: 'all' | MonitorType; label: string }> = [
    { value: 'all', label: t.filterAll },
    { value: 'http', label: 'HTTP' },
    { value: 'browser', label: 'Browser' },
  ];

  const statusFilters: Array<{ value: 'all' | MonitorStatus; label: string }> = [
    { value: 'all', label: t.filterAnyState },
    { value: 'up', label: t.filterHealthy },
    { value: 'degraded', label: t.degraded },
    { value: 'down', label: t.filterDown },
    { value: 'paused', label: t.paused },
    { value: 'pending', label: t.filterPending },
  ];

  const navigate = useNavigate();
  const meta = useMeta();
  const monitorLimit = meta?.deployment_mode === 'team' ? meta.limits?.max_monitors ?? null : null;
  const [monitors, setMonitors] = useState<Monitor[]>([]);
  const [uptimeById, setUptimeById] = useState<Record<string, MonitorUptime>>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [query, setQuery] = useState('');
  const [typeFilter, setTypeFilter] = useState<'all' | MonitorType>('all');
  const [statusFilter, setStatusFilter] = useState<'all' | MonitorStatus>('all');

  useEffect(() => {
    let ignore = false;

    Promise.all([listMonitors(), getMonitorsUptime('24h')])
      .then(([items, uptimeRows]) => {
        if (!ignore) {
          setMonitors(items);
          setUptimeById(Object.fromEntries(uptimeRows.map((row) => [row.monitor_id, row])));
          setError('');
        }
      })
      .catch((error) => {
        if (!ignore) {
          setError(error instanceof Error ? error.message : t.loadError);
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
  }, []);

  const summary = useMemo(() => {
    const down = monitors.filter((monitor) => monitor.status === 'down').length;
    const degraded = monitors.filter((monitor) => monitor.status === 'degraded').length;
    const paused = monitors.filter((monitor) => monitor.status === 'paused').length;
    const uptimeValues = monitors
      .filter((monitor) => monitor.enabled)
      .map((monitor) => uptimeById[monitor.id]?.uptime_pct)
      .filter((value): value is number => typeof value === 'number');
    const averageUptime =
      uptimeValues.length === 0
        ? null
        : Math.round((uptimeValues.reduce((sum, value) => sum + value, 0) / uptimeValues.length) * 10) / 10;

    return { averageUptime, down, degraded, paused };
  }, [monitors, uptimeById]);

  const filteredMonitors = useMemo(
    () =>
      monitors.filter((monitor) => {
        const normalizedQuery = query.trim().toLowerCase();
        const matchesQuery =
          normalizedQuery.length === 0 ||
          monitor.name.toLowerCase().includes(normalizedQuery) ||
          (monitor.url ?? '').toLowerCase().includes(normalizedQuery);
        const matchesType = typeFilter === 'all' || monitor.type === typeFilter;
        const matchesStatus = statusFilter === 'all' || monitor.status === statusFilter;

        return matchesQuery && matchesType && matchesStatus;
      }),
    [monitors, query, statusFilter, typeFilter]
  );

  return (
    <div className="space-y-6">
      <section className="overflow-hidden rounded-lg bg-card p-6 shadow-card">
        <div className="flex flex-col gap-8 xl:flex-row xl:items-end xl:justify-between">
          <div className="max-w-3xl">
            <p className="text-sm font-semibold text-primary">{t.overview}</p>
            <h1 className="mt-2 text-2xl font-semibold leading-8 text-foreground">{t.heroTitle}</h1>
            <p className="mt-3 text-sm leading-6 text-muted-foreground">{t.heroText}</p>
          </div>

          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              onClick={() => navigate('/config')}
              className="inline-flex items-center gap-2 rounded-lg bg-secondary px-4 py-[11px] text-base font-medium leading-none text-primary transition-colors hover:bg-accent"
            >
              <Workflow className="h-4 w-4" />
              {t.openConfig}
            </button>
            <button
              type="button"
              onClick={() => navigate('/monitors/new')}
              className="inline-flex items-center gap-2 rounded-lg bg-primary px-4 py-[11px] text-base font-medium leading-none text-primary-foreground transition-colors hover:bg-primary-hover"
            >
              <Plus className="h-4 w-4" />
              {t.newMonitor}
            </button>
          </div>
        </div>
      </section>

      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <SummaryCard
          title={t.fleetHealth}
          value={summary.averageUptime === null ? '—' : `${summary.averageUptime}%`}
          hint={monitors.length === 0 ? t.noMonitorsYet : t.avgUptimeHint}
          icon={Waves}
        />
        <SummaryCard title={t.downMonitors} value={String(summary.down)} hint={t.downHint} icon={Siren} />
        <SummaryCard title={t.degraded} value={String(summary.degraded)} hint={t.degradedHint} icon={AlertTriangle} />
        <SummaryCard title={t.paused} value={String(summary.paused)} hint={t.pausedHint} icon={Clock3} />
      </div>

      <div>
        <Card className="overflow-hidden">
          <CardHeader className="gap-4 border-b border-border">
            <div className="flex flex-col gap-4 xl:flex-row xl:items-center xl:justify-between">
              <div>
                <div className="flex flex-wrap items-center gap-2">
                  <CardTitle>{t.serviceRoster}</CardTitle>
                  {monitorLimit !== null && (
                    <span className="text-sm text-muted-foreground">
                      {t.monitorCount(monitors.length, monitorLimit)}
                    </span>
                  )}
                </div>
                <p className="mt-2 text-sm text-muted-foreground">{t.rosterSubtitle}</p>
              </div>

              <div className="relative w-full xl:max-w-sm">
                <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-placeholder" />
                <Input
                  value={query}
                  onChange={(event) => setQuery(event.target.value)}
                  placeholder={t.searchPlaceholder}
                  className="pl-9"
                />
              </div>
            </div>

            <div className="flex flex-col gap-3">
              <div className="flex items-center gap-2 text-xs font-semibold text-muted-foreground">
                <SlidersHorizontal className="h-3.5 w-3.5" />
                {t.filters}
              </div>
              <div className="flex flex-col gap-3 xl:flex-row xl:items-center">
                <FilterGroup values={statusFilters} activeValue={statusFilter} onChange={setStatusFilter} />
                <FilterGroup values={typeFilters} activeValue={typeFilter} onChange={setTypeFilter} />
              </div>
            </div>
          </CardHeader>

          <CardContent className="space-y-4 p-4 md:p-6">
            {loading ? (
              <div className="rounded-lg border border-dashed border-border bg-secondary p-12 text-center">
                <p className="text-lg font-semibold text-foreground">{t.loadingMonitors}</p>
              </div>
            ) : error ? (
              <div className="rounded-lg bg-destructive/10 p-12 text-center">
                <p className="text-lg font-semibold text-destructive">{t.loadError}</p>
                <p className="mt-2 text-sm text-destructive">{error}</p>
              </div>
            ) : filteredMonitors.length === 0 ? (
              <div className="rounded-lg border border-dashed border-border bg-secondary p-12 text-center">
                {monitors.length === 0 ? (
                  <>
                    <p className="text-lg font-semibold text-foreground">{t.noMonitorsYet}</p>
                    <p className="mt-2 text-sm text-placeholder">{t.emptyCreateFirst}</p>
                  </>
                ) : (
                  <>
                    <p className="text-lg font-semibold text-foreground">{t.noMatch}</p>
                    <p className="mt-2 text-sm text-placeholder">{t.noMatchHint}</p>
                  </>
                )}
              </div>
            ) : (
              filteredMonitors.map((monitor) => (
                <button
                  key={monitor.id}
                  type="button"
                  onClick={() => navigate(`/monitors/${monitor.id}`)}
                  className="w-full rounded-lg bg-card p-5 text-left shadow-card transition-shadow hover:shadow-floating"
                >
                  <div className="flex flex-col gap-5 xl:flex-row xl:items-start xl:justify-between">
                    <div className="min-w-0 flex-1">
                      <div className="flex flex-wrap items-center gap-3">
                        <h3 className="text-sm font-semibold leading-5 text-primary">{monitor.name}</h3>
                        <StatusBadge status={monitor.status} />
                        {monitor.in_maintenance && (
                          <span className="rounded-lg bg-secondary px-2.5 py-1 text-[11px] font-semibold uppercase text-muted-foreground">
                            {t.maintenance}
                          </span>
                        )}
                        <span className="rounded-lg bg-secondary px-3 py-1 text-xs font-semibold uppercase text-muted-foreground">
                          {monitor.type}
                        </span>
                        {monitor.ssl_days_left !== null && monitor.ssl_days_left !== undefined && monitor.ssl_days_left <= 14 && (
                          <span
                            className={cn(
                              'rounded-lg px-2.5 py-1 text-[11px] font-semibold uppercase',
                              monitor.ssl_days_left <= 7
                                ? 'bg-status-down/10 text-status-down'
                                : 'bg-status-degraded/15 text-status-degraded'
                            )}
                          >
                            {t.ssl(monitor.ssl_days_left)}
                          </span>
                        )}
                      </div>

                      <p className="mt-2 truncate text-sm text-muted-foreground">{monitor.url}</p>
                    </div>

                    <div className="grid min-w-[16rem] grid-cols-2 gap-3 sm:grid-cols-4 xl:grid-cols-2">
                      <Stat label={t.statUptime} value={formatUptime(uptimeById[monitor.id]?.uptime_pct)} />
                      <Stat label={t.statLastCheck} value={formatRelativeTime(uptimeById[monitor.id]?.last_check_at)} />
                      <Stat label={t.statResponse} value={t.formatResponse(uptimeById[monitor.id]?.last_response_ms)} />
                      <Stat label={t.statInterval} value={t.formatInterval(monitor.interval)} />
                    </div>
                  </div>

                  <div className="mt-4 flex items-center justify-between border-t border-border pt-4">
                    <p className="text-sm text-muted-foreground">{monitor.enabled ? t.checksEnabled : t.checksPaused}</p>
                    <span className="inline-flex items-center gap-1 text-sm font-semibold text-primary">
                      {t.openService}
                      <ChevronRight className="h-4 w-4" />
                    </span>
                  </div>
                </button>
              ))
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

function SummaryCard({
  title,
  value,
  hint,
  icon: Icon,
}: {
  title: string;
  value: string;
  hint: string;
  icon: typeof Waves;
}) {
  return (
    <Card>
      <CardContent className="space-y-4 p-5">
        <div className="flex h-11 w-11 items-center justify-center rounded-lg bg-accent text-primary">
          <Icon className="h-5 w-5" />
        </div>
        <div>
          <p className="text-sm text-muted-foreground">{title}</p>
          <p className="mt-1 text-2xl font-semibold leading-8 text-foreground">{value}</p>
          <p className="mt-2 text-xs text-placeholder">{hint}</p>
        </div>
      </CardContent>
    </Card>
  );
}

function formatUptime(uptimePct: number | null | undefined): string {
  return typeof uptimePct === 'number' ? `${uptimePct}%` : '—';
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg bg-secondary px-3 py-3">
      <p className="text-[11px] font-semibold text-placeholder">{label}</p>
      <p className="mt-1 text-sm font-semibold text-foreground">{value}</p>
    </div>
  );
}

function FilterGroup<T extends string>({
  values,
  activeValue,
  onChange,
}: {
  values: ReadonlyArray<{ value: T; label: string }>;
  activeValue: T;
  onChange: (value: T) => void;
}) {
  return (
    <div className="flex flex-wrap gap-2">
      {values.map((item) => (
        <button
          key={item.value}
          type="button"
          onClick={() => onChange(item.value)}
          className={cn(
            'rounded-lg px-3 py-1.5 text-[13px] leading-5 transition-colors',
            activeValue === item.value
              ? 'bg-accent font-semibold text-primary'
              : 'bg-secondary text-foreground hover:text-primary'
          )}
        >
          {item.label}
        </button>
      ))}
    </div>
  );
}

