import { useMemo, useState } from 'react';
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
  getDashboardSummary,
  getMonitorHealthTimeline,
  getMonitors,
  type MonitorStatus,
  type MonitorType,
} from '../data/mockMonitoring';
import { cn } from '../utils/cn';

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
];

const locationFilters = [
  { value: 'all', label: 'All regions' },
  { value: 'eu', label: 'Europe' },
  { value: 'us', label: 'US' },
  { value: 'local', label: 'Local' },
] as const;

export default function Dashboard() {
  const navigate = useNavigate();
  const monitors = getMonitors();
  const summary = getDashboardSummary();
  const [query, setQuery] = useState('');
  const [typeFilter, setTypeFilter] = useState<'all' | MonitorType>('all');
  const [statusFilter, setStatusFilter] = useState<'all' | MonitorStatus>('all');
  const [locationFilter, setLocationFilter] = useState<(typeof locationFilters)[number]['value']>('all');

  const filteredMonitors = useMemo(
    () =>
      monitors.filter((monitor) => {
        const normalizedQuery = query.trim().toLowerCase();
        const matchesQuery =
          normalizedQuery.length === 0 ||
          monitor.name.toLowerCase().includes(normalizedQuery) ||
          monitor.url.toLowerCase().includes(normalizedQuery) ||
          monitor.location.toLowerCase().includes(normalizedQuery);
        const matchesType = typeFilter === 'all' || monitor.type === typeFilter;
        const matchesStatus = statusFilter === 'all' || monitor.status === statusFilter;
        const matchesLocation =
          locationFilter === 'all' ||
          (locationFilter === 'eu' && monitor.location.startsWith('eu-')) ||
          (locationFilter === 'us' && monitor.location.startsWith('us-')) ||
          (locationFilter === 'local' && monitor.location.startsWith('local'));

        return matchesQuery && matchesType && matchesStatus && matchesLocation;
      }),
    [locationFilter, monitors, query, statusFilter, typeFilter]
  );

  const highlightedIncident = monitors.find((monitor) => monitor.status === 'down') ?? monitors[0];

  return (
    <div className="space-y-6">
      <section className="overflow-hidden rounded-[2rem] border border-slate-200 bg-[linear-gradient(135deg,_#0f172a_0%,_#113b3a_45%,_#d7efe8_160%)] p-6 text-white shadow-[0_30px_80px_rgba(15,23,42,0.14)]">
        <div className="flex flex-col gap-8 xl:flex-row xl:items-end xl:justify-between">
          <div className="max-w-3xl">
            <p className="text-sm font-semibold uppercase tracking-[0.26em] text-teal-200">Operational overview</p>
            <h1 className="mt-3 text-3xl font-semibold tracking-tight md:text-4xl">Состояние сервисов за период видно сразу</h1>
            <p className="mt-3 text-sm leading-7 text-slate-200/90">
              Карточки ниже показывают не только текущий статус, но и недавнюю историю работоспособности. Это удобнее
              для быстрого triage, чем отдельные теги и декоративные элементы.
            </p>
          </div>

          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              onClick={() => navigate('/config')}
              className="inline-flex h-11 items-center gap-2 rounded-xl border border-white/15 bg-white/10 px-4 text-sm font-medium text-white transition-colors hover:bg-white/16"
            >
              <Workflow className="h-4 w-4" />
              Open config
            </button>
            <button
              type="button"
              onClick={() => navigate('/monitors/new')}
              className="inline-flex h-11 items-center gap-2 rounded-xl bg-white px-4 text-sm font-semibold text-slate-950 transition-colors hover:bg-teal-50"
            >
              <Plus className="h-4 w-4" />
              New monitor
            </button>
          </div>
        </div>
      </section>

      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <SummaryCard title="Fleet health" value={`${summary.averageUptime}%`} hint="Average uptime over the last 24h" icon={Waves} />
        <SummaryCard title="Down monitors" value={String(summary.down)} hint="Require immediate action" icon={Siren} />
        <SummaryCard title="Degraded" value={String(summary.degraded)} hint="Slow or unstable checks" icon={AlertTriangle} />
        <SummaryCard title="Paused" value={String(summary.paused)} hint="Temporarily excluded from checks" icon={Clock3} />
      </div>

      <div className="grid gap-6 xl:grid-cols-[1.3fr_0.7fr]">
        <Card className="overflow-hidden">
          <CardHeader className="gap-4 border-b border-slate-200 bg-slate-50/70">
            <div className="flex flex-col gap-4 xl:flex-row xl:items-center xl:justify-between">
              <div>
                <CardTitle className="text-xl">Service roster</CardTitle>
                <p className="mt-2 text-sm text-slate-600">Поиск и фильтры вместо облака тегов.</p>
              </div>

              <div className="relative w-full xl:max-w-sm">
                <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
                <Input
                  value={query}
                  onChange={(event) => setQuery(event.target.value)}
                  placeholder="Search by name, URL, region..."
                  className="pl-9"
                />
              </div>
            </div>

            <div className="flex flex-col gap-3">
              <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.22em] text-slate-500">
                <SlidersHorizontal className="h-3.5 w-3.5" />
                Filters
              </div>
              <div className="flex flex-col gap-3 xl:flex-row xl:items-center">
                <FilterGroup values={statusFilters} activeValue={statusFilter} onChange={setStatusFilter} />
                <FilterGroup values={typeFilters} activeValue={typeFilter} onChange={setTypeFilter} />
                <FilterGroup values={locationFilters} activeValue={locationFilter} onChange={setLocationFilter} />
              </div>
            </div>
          </CardHeader>

          <CardContent className="space-y-4 p-4 md:p-6">
            {filteredMonitors.length === 0 ? (
              <div className="rounded-[1.5rem] border border-dashed border-slate-200 bg-slate-50 p-12 text-center">
                <p className="text-lg font-semibold text-slate-900">No monitors match these filters</p>
                <p className="mt-2 text-sm text-slate-500">Попробуйте сбросить один из фильтров или изменить запрос.</p>
              </div>
            ) : (
              filteredMonitors.map((monitor) => (
                <button
                  key={monitor.id}
                  type="button"
                  onClick={() => navigate(`/monitors/${monitor.id}`)}
                  className="w-full rounded-[1.5rem] border border-slate-200 bg-white p-5 text-left transition-all hover:-translate-y-0.5 hover:border-teal-200 hover:shadow-[0_18px_40px_rgba(15,23,42,0.08)]"
                >
                  <div className="flex flex-col gap-5 xl:flex-row xl:items-start xl:justify-between">
                    <div className="min-w-0 flex-1">
                      <div className="flex flex-wrap items-center gap-3">
                        <h3 className="text-lg font-semibold text-slate-950">{monitor.name}</h3>
                        <StatusBadge status={monitor.status} />
                        <span className="rounded-full bg-slate-100 px-3 py-1 text-xs font-semibold uppercase tracking-[0.2em] text-slate-600">
                          {monitor.type}
                        </span>
                      </div>

                      <p className="mt-2 truncate text-sm text-slate-600">{monitor.url}</p>

                      <div className="mt-4 rounded-[1.25rem] border border-slate-200 bg-slate-50 p-4">
                        <div className="flex items-center justify-between gap-3">
                          <div>
                            <p className="text-xs font-semibold uppercase tracking-[0.2em] text-slate-500">Uptime period</p>
                            <p className="mt-1 text-sm text-slate-700">Последние 20 интервалов проверки</p>
                          </div>
                          <p className="text-sm font-semibold text-slate-900">{monitor.uptime24h}%</p>
                        </div>
                        <HealthTimeline monitorId={monitor.id} />
                      </div>
                    </div>

                    <div className="grid min-w-[16rem] grid-cols-2 gap-3 sm:grid-cols-4 xl:grid-cols-2">
                      <Stat label="Response" value={monitor.responseTimeMs ? `${monitor.responseTimeMs} ms` : 'No data'} />
                      <Stat label="Region" value={monitor.location} />
                      <Stat label="Interval" value={`${Math.round(monitor.intervalSeconds / 60)} min`} />
                      <Stat label="Last check" value={monitor.lastCheckedAt.slice(11, 16)} />
                    </div>
                  </div>

                  <div className="mt-4 flex items-center justify-between border-t border-slate-100 pt-4">
                    <p className="text-sm text-slate-600">{monitor.summary}</p>
                    <span className="inline-flex items-center gap-1 text-sm font-semibold text-teal-800">
                      Open service
                      <ChevronRight className="h-4 w-4" />
                    </span>
                  </div>
                </button>
              ))
            )}
          </CardContent>
        </Card>

        <div className="space-y-6">
          <Card className="overflow-hidden border-rose-200 bg-[linear-gradient(180deg,_#fff7f7_0%,_#fff2f2_100%)]">
            <CardHeader>
              <CardTitle className="text-xl text-rose-900">Incident in focus</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <StatusBadge status={highlightedIncident.status} className="bg-white" />
              <div>
                <p className="text-lg font-semibold text-slate-950">{highlightedIncident.name}</p>
                <p className="mt-2 text-sm leading-6 text-slate-600">{highlightedIncident.summary}</p>
              </div>
              <div className="rounded-2xl border border-rose-200 bg-white px-4 py-3 text-sm text-slate-700">
                Last incident started at {highlightedIncident.lastIncidentAt ?? 'No incident timestamp'}.
              </div>
              <button
                type="button"
                onClick={() => navigate(`/monitors/${highlightedIncident.id}/history`)}
                className="inline-flex items-center gap-2 text-sm font-semibold text-rose-800 hover:text-rose-700"
              >
                Open history
                <ChevronRight className="h-4 w-4" />
              </button>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="text-xl">Quick read</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3 text-sm text-slate-600">
              <ChecklistRow checked label="Each service card shows a visual uptime period strip." />
              <ChecklistRow checked label="Tags removed from the main list in favor of filters." />
              <ChecklistRow checked label="Clicks use direct navigation handlers for monitor and config screens." />
              <ChecklistRow checked label="List is quieter visually and focuses on operational signal." />
            </CardContent>
          </Card>
        </div>
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
    <Card className="border-slate-200 bg-white">
      <CardContent className="space-y-4 p-5">
        <div className="flex h-11 w-11 items-center justify-center rounded-2xl bg-teal-50 text-teal-700">
          <Icon className="h-5 w-5" />
        </div>
        <div>
          <p className="text-sm text-slate-500">{title}</p>
          <p className="mt-1 text-3xl font-semibold text-slate-950">{value}</p>
          <p className="mt-2 text-xs text-slate-500">{hint}</p>
        </div>
      </CardContent>
    </Card>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-[1rem] border border-slate-200 bg-slate-50 px-3 py-3">
      <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-slate-500">{label}</p>
      <p className="mt-1 text-sm font-semibold text-slate-900">{value}</p>
    </div>
  );
}

function HealthTimeline({ monitorId }: { monitorId: string }) {
  const timeline = getMonitorHealthTimeline(monitorId);

  return (
    <div className="mt-4 grid grid-cols-10 gap-1">
      {timeline.map((status, index) => (
        <div
          key={`${monitorId}-${index}`}
          className={cn(
            'h-3 rounded-full',
            status === 'up' && 'bg-emerald-500',
            status === 'degraded' && 'bg-amber-400',
            status === 'down' && 'bg-rose-500',
            status === 'paused' && 'bg-slate-300'
          )}
          title={`Interval ${index + 1}: ${status}`}
        />
      ))}
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
            'rounded-full border px-3 py-2 text-sm font-medium transition-colors',
            activeValue === item.value
              ? 'border-teal-900 bg-teal-900 text-white'
              : 'border-slate-200 bg-white text-slate-600 hover:border-slate-300 hover:bg-slate-50'
          )}
        >
          {item.label}
        </button>
      ))}
    </div>
  );
}

function ChecklistRow({ checked, label }: { checked: boolean; label: string }) {
  return (
    <div className="flex items-start gap-3 rounded-2xl border border-slate-200 p-3">
      <div className={cn('mt-0.5 h-2.5 w-2.5 rounded-full', checked ? 'bg-emerald-500' : 'bg-slate-300')} />
      <p>{label}</p>
    </div>
  );
}
