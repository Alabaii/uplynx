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
import { cn } from '../utils/cn';
import { formatRelativeTime } from '../utils/time';

const typeFilters: Array<{ value: 'all' | MonitorType; label: string }> = [
  { value: 'all', label: 'All' },
  { value: 'http', label: 'HTTP' },
  { value: 'browser', label: 'Browser' },
];

const statusFilters: Array<{ value: 'all' | MonitorStatus; label: string }> = [
  { value: 'all', label: 'Any state' },
  { value: 'up', label: 'Healthy' },
  { value: 'degraded', label: 'Degraded' },
  { value: 'down', label: 'Down' },
  { value: 'paused', label: 'Paused' },
  { value: 'pending', label: 'Pending' },
];

export default function Dashboard() {
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
          setError(error instanceof Error ? error.message : 'Unable to load monitors');
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
            <p className="text-sm font-semibold text-primary">Operational overview</p>
            <h1 className="mt-2 text-2xl font-semibold leading-8 text-foreground">Fleet status at a glance</h1>
            <p className="mt-3 text-sm leading-6 text-muted-foreground">
              Every card below reflects the live state reported by the checks pipeline. Open a service to see its
              response history, or jump straight into the config to change what is monitored.
            </p>
          </div>

          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              onClick={() => navigate('/config')}
              className="inline-flex items-center gap-2 rounded-lg bg-secondary px-4 py-[11px] text-base font-medium leading-none text-primary transition-colors hover:bg-accent"
            >
              <Workflow className="h-4 w-4" />
              Open config
            </button>
            <button
              type="button"
              onClick={() => navigate('/monitors/new')}
              className="inline-flex items-center gap-2 rounded-lg bg-primary px-4 py-[11px] text-base font-medium leading-none text-primary-foreground transition-colors hover:bg-primary-hover"
            >
              <Plus className="h-4 w-4" />
              New monitor
            </button>
          </div>
        </div>
      </section>

      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <SummaryCard
          title="Fleet health"
          value={summary.averageUptime === null ? '—' : `${summary.averageUptime}%`}
          hint={monitors.length === 0 ? 'No monitors yet' : 'Average uptime over the last 24h'}
          icon={Waves}
        />
        <SummaryCard title="Down monitors" value={String(summary.down)} hint="Require immediate action" icon={Siren} />
        <SummaryCard title="Degraded" value={String(summary.degraded)} hint="Slow or unstable checks" icon={AlertTriangle} />
        <SummaryCard title="Paused" value={String(summary.paused)} hint="Temporarily excluded from checks" icon={Clock3} />
      </div>

      <div>
        <Card className="overflow-hidden">
          <CardHeader className="gap-4 border-b border-border">
            <div className="flex flex-col gap-4 xl:flex-row xl:items-center xl:justify-between">
              <div>
                <div className="flex flex-wrap items-center gap-2">
                  <CardTitle>Service roster</CardTitle>
                  {monitorLimit !== null && (
                    <span className="text-sm text-muted-foreground">
                      {monitors.length} / {monitorLimit} monitors
                    </span>
                  )}
                </div>
                <p className="mt-2 text-sm text-muted-foreground">Search and filter the monitored services.</p>
              </div>

              <div className="relative w-full xl:max-w-sm">
                <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-placeholder" />
                <Input
                  value={query}
                  onChange={(event) => setQuery(event.target.value)}
                  placeholder="Search by name or URL..."
                  className="pl-9"
                />
              </div>
            </div>

            <div className="flex flex-col gap-3">
              <div className="flex items-center gap-2 text-xs font-semibold text-muted-foreground">
                <SlidersHorizontal className="h-3.5 w-3.5" />
                Filters
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
                <p className="text-lg font-semibold text-foreground">Loading monitors...</p>
              </div>
            ) : error ? (
              <div className="rounded-lg bg-destructive/10 p-12 text-center">
                <p className="text-lg font-semibold text-destructive">Unable to load monitors</p>
                <p className="mt-2 text-sm text-destructive">{error}</p>
              </div>
            ) : filteredMonitors.length === 0 ? (
              <div className="rounded-lg border border-dashed border-border bg-secondary p-12 text-center">
                {monitors.length === 0 ? (
                  <>
                    <p className="text-lg font-semibold text-foreground">No monitors yet</p>
                    <p className="mt-2 text-sm text-placeholder">Create your first monitor or upload a config to get started.</p>
                  </>
                ) : (
                  <>
                    <p className="text-lg font-semibold text-foreground">No monitors match these filters</p>
                    <p className="mt-2 text-sm text-placeholder">Try resetting a filter or adjusting the search query.</p>
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
                            Maintenance
                          </span>
                        )}
                        <span className="rounded-lg bg-secondary px-3 py-1 text-xs font-semibold uppercase text-muted-foreground">
                          {monitor.type}
                        </span>
                      </div>

                      <p className="mt-2 truncate text-sm text-muted-foreground">{monitor.url}</p>
                    </div>

                    <div className="grid min-w-[16rem] grid-cols-2 gap-3 sm:grid-cols-4 xl:grid-cols-2">
                      <Stat label="Uptime 24h" value={formatUptime(uptimeById[monitor.id]?.uptime_pct)} />
                      <Stat label="Last check" value={formatRelativeTime(uptimeById[monitor.id]?.last_check_at)} />
                      <Stat label="Response" value={formatResponse(uptimeById[monitor.id]?.last_response_ms)} />
                      <Stat label="Interval" value={formatInterval(monitor.interval)} />
                    </div>
                  </div>

                  <div className="mt-4 flex items-center justify-between border-t border-border pt-4">
                    <p className="text-sm text-muted-foreground">{monitor.enabled ? 'Scheduled checks enabled' : 'Checks paused'}</p>
                    <span className="inline-flex items-center gap-1 text-sm font-semibold text-primary">
                      Open service
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

function formatInterval(seconds: number): string {
  return seconds < 60 ? `${seconds} s` : `${Math.round(seconds / 60)} min`;
}

function formatUptime(uptimePct: number | null | undefined): string {
  return typeof uptimePct === 'number' ? `${uptimePct}%` : '—';
}

function formatResponse(responseMs: number | null | undefined): string {
  return typeof responseMs === 'number' ? `${responseMs} ms` : '—';
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

