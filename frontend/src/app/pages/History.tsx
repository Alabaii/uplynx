import { useMemo, useState } from 'react';
import { Link, Navigate, useParams } from 'react-router';
import { ArrowLeft, FileClock, Filter, HistoryIcon, ScrollText } from 'lucide-react';
import { Button } from '../components/ui/Button';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/Card';
import { StatusBadge } from '../components/StatusBadge';
import { getChecksForMonitor, getIncidentsForMonitor, getMonitorById, type MonitorStatus } from '../data/mockMonitoring';
import { cn } from '../utils/cn';

const ranges = ['1h', '24h', '7d', '30d'] as const;

export default function History() {
  const { id = '' } = useParams();
  const monitor = getMonitorById(id);
  const [range, setRange] = useState<(typeof ranges)[number]>('24h');
  const [statusFilter, setStatusFilter] = useState<'all' | MonitorStatus>('all');

  if (!monitor) {
    return <Navigate to="/" replace />;
  }

  const checks = getChecksForMonitor(monitor.id);
  const incidents = getIncidentsForMonitor(monitor.id);
  const filteredChecks = useMemo(
    () => checks.filter((check) => (statusFilter === 'all' ? true : check.status === statusFilter)),
    [checks, statusFilter]
  );

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <Link to={`/monitors/${monitor.id}`} className="inline-flex h-10 w-10 items-center justify-center rounded-full border border-slate-200 bg-white text-slate-600 transition-colors hover:border-slate-300 hover:text-slate-900">
            <ArrowLeft className="h-5 w-5" />
          </Link>
          <div>
            <p className="text-sm font-semibold uppercase tracking-[0.22em] text-teal-700">Monitor history</p>
            <h1 className="text-3xl font-semibold tracking-tight text-slate-950">{monitor.name}</h1>
          </div>
        </div>

        <div className="flex flex-wrap gap-2">
          {ranges.map((item) => (
            <button
              key={item}
              type="button"
              onClick={() => setRange(item)}
              className={cn(
                'rounded-full px-3 py-2 text-sm font-semibold transition-colors',
                range === item ? 'bg-teal-900 text-white' : 'bg-white text-slate-600 hover:bg-slate-100'
              )}
            >
              {item}
            </button>
          ))}
        </div>
      </div>

      <div className="grid gap-6 xl:grid-cols-[0.8fr_1.2fr]">
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-xl">
              <HistoryIcon className="h-5 w-5 text-teal-700" />
              Incident timeline
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            {incidents.length === 0 ? (
              <div className="rounded-2xl border border-dashed border-slate-200 bg-slate-50 p-8 text-center text-sm text-slate-500">
                No incidents in the selected range.
              </div>
            ) : (
              incidents.map((incident) => (
                <div key={incident.id} className="rounded-[1.5rem] border border-slate-200 p-4">
                  <div className="flex items-center justify-between gap-3">
                    <p className="font-semibold text-slate-900">{incident.title}</p>
                    <span className="rounded-full bg-slate-100 px-3 py-1 text-xs font-semibold uppercase tracking-[0.18em] text-slate-600">
                      {incident.severity}
                    </span>
                  </div>
                  <p className="mt-3 text-sm leading-6 text-slate-600">{incident.impact}</p>
                  <p className="mt-3 text-xs text-slate-500">
                    {incident.startedAt}
                    {incident.resolvedAt ? ` → ${incident.resolvedAt}` : ' → open'}
                  </p>
                </div>
              ))
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="gap-4 border-b border-slate-200 bg-slate-50/80">
            <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
              <div>
                <CardTitle className="flex items-center gap-2 text-xl">
                  <ScrollText className="h-5 w-5 text-teal-700" />
                  Check log
                </CardTitle>
                <p className="mt-2 text-sm text-slate-600">Current range: {range}. Filter recent results by state.</p>
              </div>

              <div className="flex flex-wrap gap-2">
                {(['all', 'up', 'degraded', 'down', 'paused'] as const).map((item) => (
                  <button
                    key={item}
                    type="button"
                    onClick={() => setStatusFilter(item)}
                    className={cn(
                      'rounded-full px-3 py-2 text-sm font-medium transition-colors',
                      statusFilter === item ? 'bg-teal-900 text-white' : 'bg-white text-slate-600 hover:bg-slate-100'
                    )}
                  >
                    {item === 'all' ? 'All' : item}
                  </button>
                ))}
              </div>
            </div>
          </CardHeader>

          <CardContent className="space-y-4 p-4 md:p-6">
            {filteredChecks.length === 0 ? (
              <div className="rounded-2xl border border-dashed border-slate-200 bg-slate-50 p-10 text-center text-sm text-slate-500">
                No checks match the selected filters.
              </div>
            ) : (
              filteredChecks.map((check) => (
                <div key={check.id} className="rounded-[1.5rem] border border-slate-200 p-4">
                  <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
                    <div className="space-y-3">
                      <div className="flex flex-wrap items-center gap-3">
                        <StatusBadge status={check.status} />
                        <p className="text-sm font-medium text-slate-900">{check.timestamp}</p>
                        <span className="inline-flex items-center gap-1 rounded-full bg-slate-100 px-3 py-1 text-xs text-slate-600">
                          <Filter className="h-3 w-3" />
                          {check.location}
                        </span>
                      </div>

                      <div className="rounded-2xl bg-slate-50 p-4 text-sm leading-6 text-slate-600">
                        {check.error ? <p className="font-medium text-rose-700">{check.error}</p> : <p>Check completed successfully.</p>}
                        <div className="mt-3 space-y-1 font-mono text-xs text-slate-500">
                          {check.logLines.map((line) => (
                            <div key={line}>{line}</div>
                          ))}
                        </div>
                      </div>
                    </div>

                    <div className="rounded-2xl border border-slate-200 px-4 py-3 text-right">
                      <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-slate-500">Response</p>
                      <p className="mt-1 text-lg font-semibold text-slate-950">
                        {check.responseTimeMs ? `${check.responseTimeMs} ms` : 'No response'}
                      </p>
                    </div>
                  </div>
                </div>
              ))
            )}
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardContent className="flex flex-col gap-4 p-6 lg:flex-row lg:items-center lg:justify-between">
          <div>
            <p className="text-sm font-semibold text-slate-900">Archive policy preview</p>
            <p className="mt-2 text-sm leading-6 text-slate-600">
              PRD note: raw history is retained for one year and later summarized into uptime percentages and exports.
            </p>
          </div>
          <Button variant="outline" className="gap-2">
            <FileClock className="h-4 w-4" />
            Export mock history
          </Button>
        </CardContent>
      </Card>
    </div>
  );
}
