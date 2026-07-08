import { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router';
import { Siren } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/Card';
import { StatusBadge } from '../components/StatusBadge';
import { listIncidents, type Incident, type IncidentStatus } from '../api';
import { cn } from '../utils/cn';
import { formatDuration, formatRelativeTime } from '../utils/time';

const ranges = ['24h', '7d', '30d'] as const;

const statusFilters: Array<{ value: 'all' | IncidentStatus; label: string }> = [
  { value: 'all', label: 'All' },
  { value: 'open', label: 'Open' },
  { value: 'resolved', label: 'Resolved' },
];

export default function Incidents() {
  const [incidents, setIncidents] = useState<Incident[]>([]);
  const [statusFilter, setStatusFilter] = useState<'all' | IncidentStatus>('all');
  const [range, setRange] = useState<(typeof ranges)[number]>('7d');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    let ignore = false;

    setLoading(true);

    listIncidents({ range, status: statusFilter === 'all' ? undefined : statusFilter, limit: 200 })
      .then((rows) => {
        if (!ignore) {
          setIncidents(rows);
          setError('');
        }
      })
      .catch((error) => {
        if (!ignore) {
          setError(error instanceof Error ? error.message : 'Unable to load incidents');
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
  }, [range, statusFilter]);

  const openCount = useMemo(() => incidents.filter((incident) => incident.status === 'open').length, [incidents]);

  return (
    <div className="space-y-6">
      <section className="overflow-hidden rounded-lg bg-card p-6 shadow-card">
        <div className="flex flex-col gap-6 xl:flex-row xl:items-end xl:justify-between">
          <div className="max-w-3xl">
            <p className="text-sm font-semibold text-primary">Reliability timeline</p>
            <h1 className="mt-2 text-2xl font-semibold leading-8 text-foreground">Incident history</h1>
            <p className="mt-3 text-sm leading-6 text-muted-foreground">
              Every period a service dropped out of the healthy state, opened automatically when it went down or
              degraded and resolved when it recovered.
            </p>
          </div>

          <div className="flex items-center gap-3 rounded-lg bg-secondary px-4 py-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-accent text-primary">
              <Siren className="h-5 w-5" />
            </div>
            <div>
              <p className="text-xs text-placeholder">Currently open</p>
              <p className="text-2xl font-semibold leading-7 text-foreground">{openCount}</p>
            </div>
          </div>
        </div>
      </section>

      {error && <div className="rounded-lg bg-destructive/10 p-4 text-sm text-destructive">{error}</div>}

      <Card className="overflow-hidden">
        <CardHeader className="gap-4 border-b border-border">
          <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
            <CardTitle className="flex items-center gap-2">
              <Siren className="h-5 w-5 text-primary" />
              Incidents
            </CardTitle>

            <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
              <FilterGroup values={statusFilters} activeValue={statusFilter} onChange={setStatusFilter} />
              <FilterGroup
                values={ranges.map((item) => ({ value: item, label: item }))}
                activeValue={range}
                onChange={setRange}
              />
            </div>
          </div>
        </CardHeader>

        <CardContent className="space-y-3 p-4 md:p-6">
          {loading ? (
            <div className="rounded-lg border border-dashed border-border bg-secondary p-12 text-center">
              <p className="text-lg font-semibold text-foreground">Loading incidents...</p>
            </div>
          ) : incidents.length === 0 ? (
            <div className="rounded-lg border border-dashed border-border bg-secondary p-12 text-center">
              <p className="text-lg font-semibold text-foreground">No incidents in this range</p>
              <p className="mt-2 text-sm text-placeholder">
                Services stayed healthy, or nothing matched the selected filters.
              </p>
            </div>
          ) : (
            incidents.map((incident) => <IncidentRow key={incident.id} incident={incident} />)
          )}
        </CardContent>
      </Card>
    </div>
  );
}

function IncidentRow({ incident }: { incident: Incident }) {
  return (
    <div className="rounded-lg border border-border p-4">
      <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
        <div className="min-w-0 space-y-2">
          <div className="flex flex-wrap items-center gap-3">
            <StatusBadge status={incident.severity} />
            <Link
              to={`/monitors/${incident.monitor_slug}`}
              className="text-sm font-semibold text-primary hover:underline"
            >
              {incident.monitor_name}
            </Link>
          </div>
          <p className="text-sm text-muted-foreground">Started {formatRelativeTime(incident.started_at)}</p>
          {incident.trigger_error && (
            <p className="truncate text-xs text-placeholder">{incident.trigger_error}</p>
          )}
        </div>

        <div className="shrink-0">
          {incident.status === 'open' ? (
            <span className="inline-flex items-center rounded-lg bg-status-down/10 px-2.5 py-1 text-xs font-semibold text-status-down">
              Ongoing
            </span>
          ) : (
            <div className="rounded-lg border border-border px-4 py-2 text-right">
              <p className="text-[11px] font-semibold text-placeholder">Duration</p>
              <p className="mt-0.5 text-sm font-semibold text-foreground">
                {formatDuration(incident.duration_seconds)}
              </p>
            </div>
          )}
        </div>
      </div>
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
