import { Navigate, useNavigate, useParams } from 'react-router';
import {
  AlertTriangle,
  ArrowRight,
  Clock3,
  FileText,
  Globe,
  ServerCog,
  Zap,
} from 'lucide-react';
import {
  getChecksForMonitor,
  getIncidentsForMonitor,
  getMonitorById,
  getResponseSeries,
  getResponseSummary,
} from '../data/mockMonitoring';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/Card';
import { Button } from '../components/ui/Button';
import { StatusBadge } from '../components/StatusBadge';
import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';

export default function MonitorDetails() {
  const { id = '' } = useParams();
  const navigate = useNavigate();
  const monitor = getMonitorById(id);

  if (!monitor) {
    return <Navigate to="/" replace />;
  }

  const recentChecks = getChecksForMonitor(monitor.id);
  const incidents = getIncidentsForMonitor(monitor.id);
  const responseSeries = getResponseSeries(monitor.id);
  const responseSummary = getResponseSummary(monitor.id);

  return (
    <div className="space-y-6">
      <section className="rounded-[1.75rem] border border-slate-200 bg-white p-6 shadow-sm">
        <div className="flex flex-col gap-6 xl:flex-row xl:items-start xl:justify-between">
          <div className="space-y-4">
            <div className="flex flex-wrap items-center gap-3">
              <StatusBadge status={monitor.status} />
              <span className="rounded-full bg-slate-100 px-3 py-1 text-xs font-semibold uppercase tracking-[0.22em] text-slate-600">
                {monitor.type}
              </span>
              <span className="rounded-full bg-teal-50 px-3 py-1 text-xs font-semibold text-teal-700">
                {monitor.location}
              </span>
            </div>
            <div>
              <h1 className="text-3xl font-semibold tracking-tight text-slate-950">{monitor.name}</h1>
              <p className="mt-2 flex items-center gap-2 text-sm text-slate-600">
                <Globe className="h-4 w-4 text-slate-400" />
                {monitor.url}
              </p>
              <p className="mt-3 max-w-3xl text-sm leading-6 text-slate-600">{monitor.summary}</p>
            </div>
          </div>

          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              onClick={() => navigate(`/monitors/${monitor.id}/history`)}
              className="inline-flex h-10 items-center gap-2 rounded-lg border border-slate-300 bg-transparent px-4 py-2 text-sm font-medium text-slate-700 transition-colors hover:bg-slate-50"
            >
              View history
              <ArrowRight className="h-4 w-4" />
            </button>
            <Button className="bg-teal-900 hover:bg-teal-800">Run mock check</Button>
          </div>
        </div>
      </section>

      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <MetricCard label="24h uptime" value={`${monitor.uptime24h}%`} hint="Across scheduled checks" icon={Zap} />
        <MetricCard
          label="Average response"
          value={responseSummary.averageMs ? `${responseSummary.averageMs} ms` : 'No data'}
          hint="From recent successful checks"
          icon={Clock3}
        />
        <MetricCard label="Incidents" value={String(incidents.length)} hint="Open and recent alerts" icon={AlertTriangle} />
        <MetricCard
          label="Interval"
          value={`${Math.round(monitor.intervalSeconds / 60)} min`}
          hint="Scheduler cadence"
          icon={ServerCog}
        />
      </div>

      <div className="grid gap-6 xl:grid-cols-[1.2fr_0.8fr]">
        <Card>
          <CardHeader>
            <CardTitle className="text-xl">Response pattern</CardTitle>
          </CardHeader>
          <CardContent>
            {responseSeries.length === 0 ? (
              <div className="rounded-2xl border border-dashed border-slate-200 bg-slate-50 p-10 text-center text-sm text-slate-500">
                No response data for this monitor yet.
              </div>
            ) : (
              <div className="h-72">
                <ResponsiveContainer width="100%" height="100%">
                  <AreaChart data={responseSeries} margin={{ top: 16, right: 12, left: -20, bottom: 0 }}>
                    <defs>
                      <linearGradient id="monitor-response" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="0%" stopColor="#0f766e" stopOpacity={0.35} />
                        <stop offset="100%" stopColor="#0f766e" stopOpacity={0.02} />
                      </linearGradient>
                    </defs>
                    <CartesianGrid vertical={false} stroke="#e2e8f0" strokeDasharray="3 3" />
                    <XAxis dataKey="label" axisLine={false} tickLine={false} tick={{ fill: '#64748b', fontSize: 12 }} />
                    <YAxis axisLine={false} tickLine={false} tick={{ fill: '#64748b', fontSize: 12 }} />
                    <Tooltip
                      cursor={{ stroke: '#99f6e4', strokeWidth: 1 }}
                      contentStyle={{ borderRadius: 16, border: '1px solid #d1fae5', boxShadow: '0 16px 40px rgba(15, 23, 42, 0.12)' }}
                    />
                    <Area
                      type="monotone"
                      dataKey="responseTimeMs"
                      stroke="#0f766e"
                      strokeWidth={2.5}
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
            <CardTitle className="text-xl">Config summary</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4 text-sm text-slate-600">
            {monitor.expected && (
              <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
                <p className="font-semibold text-slate-900">HTTP expectations</p>
                <p className="mt-2">Status: {monitor.expected.status}</p>
                <p>Body contains: {monitor.expected.bodyContains}</p>
              </div>
            )}

            {monitor.steps && (
              <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
                <p className="font-semibold text-slate-900">Browser scenario</p>
                <div className="mt-3 space-y-3">
                  {monitor.steps.map((step, index) => (
                    <div key={step.id} className="flex gap-3">
                      <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-white text-xs font-semibold text-slate-700">
                        {index + 1}
                      </div>
                      <div>
                        <p className="font-medium text-slate-900">{step.label}</p>
                        <p className="text-xs text-slate-500">
                          {step.url ?? step.selector ?? step.expectedText ?? step.value}
                        </p>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            <div className="rounded-2xl border border-slate-200 bg-slate-50 p-4">
              <p className="font-semibold text-slate-900">Last check logs</p>
              <div className="mt-3 space-y-2 font-mono text-xs text-slate-600">
                {(recentChecks[0]?.logLines ?? ['No logs available']).map((line) => (
                  <div key={line}>{line}</div>
                ))}
              </div>
            </div>
          </CardContent>
        </Card>
      </div>

      <div className="grid gap-6 xl:grid-cols-[0.9fr_1.1fr]">
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-xl">
              <AlertTriangle className="h-5 w-5 text-amber-600" />
              Incident timeline
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            {incidents.length === 0 ? (
              <div className="rounded-2xl border border-dashed border-slate-200 bg-slate-50 p-8 text-center text-sm text-slate-500">
                No incidents for this monitor.
              </div>
            ) : (
              incidents.map((incident) => (
                <div key={incident.id} className="rounded-2xl border border-slate-200 p-4">
                  <p className="text-sm font-semibold text-slate-900">{incident.title}</p>
                  <p className="mt-2 text-xs uppercase tracking-[0.2em] text-slate-500">{incident.severity}</p>
                  <p className="mt-2 text-sm text-slate-600">{incident.impact}</p>
                  <p className="mt-3 text-xs text-slate-500">
                    Started {incident.startedAt}
                    {incident.resolvedAt ? ` | Resolved ${incident.resolvedAt}` : ' | Still open'}
                  </p>
                </div>
              ))
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-xl">
              <FileText className="h-5 w-5 text-teal-700" />
              Recent checks
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            {recentChecks.map((check) => (
              <div key={check.id} className="rounded-2xl border border-slate-200 p-4">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div className="flex items-center gap-3">
                    <StatusBadge status={check.status} />
                    <p className="text-sm font-medium text-slate-900">{check.timestamp}</p>
                  </div>
                  <p className="text-sm text-slate-600">
                    {check.responseTimeMs ? `${check.responseTimeMs} ms` : check.error ?? 'No response'}
                  </p>
                </div>
                <div className="mt-3 text-xs leading-6 text-slate-500">
                  {check.logLines.map((line) => (
                    <div key={line}>{line}</div>
                  ))}
                </div>
              </div>
            ))}
          </CardContent>
        </Card>
      </div>
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
        <div className="flex h-10 w-10 items-center justify-center rounded-2xl bg-teal-50 text-teal-700">
          <Icon className="h-5 w-5" />
        </div>
        <div>
          <p className="text-sm text-slate-500">{label}</p>
          <p className="mt-1 text-2xl font-semibold text-slate-950">{value}</p>
          <p className="mt-2 text-xs text-slate-500">{hint}</p>
        </div>
      </CardContent>
    </Card>
  );
}
