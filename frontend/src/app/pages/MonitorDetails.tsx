import { useEffect, useMemo, useState } from 'react';
import { Navigate, useNavigate, useParams } from 'react-router';
import {
  ArrowRight,
  Clock3,
  FileText,
  Globe,
  ServerCog,
  Zap,
} from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/Card';
import { StatusBadge } from '../components/StatusBadge';
import {
  ApiError,
  getHistory,
  getMonitor,
  getStatusLabel,
  type CheckResult,
  type Monitor,
} from '../api';
import { cn } from '../utils/cn';
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
  const { id = '' } = useParams();
  const navigate = useNavigate();
  const [monitor, setMonitor] = useState<Monitor | null>(null);
  const [checks, setChecks] = useState<CheckResult[]>([]);
  const [range, setRange] = useState<(typeof ranges)[number]>('24h');
  const [loading, setLoading] = useState(true);
  const [notFound, setNotFound] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    let ignore = false;

    setLoading(true);

    Promise.all([getMonitor(id), getHistory({ monitorId: id, range })])
      .then(([monitorData, history]) => {
        if (!ignore) {
          setMonitor(monitorData);
          setChecks(history);
          setError('');
        }
      })
      .catch((error) => {
        if (!ignore) {
          if (error instanceof ApiError && error.status === 404) {
            setNotFound(true);
          } else {
            setError(error instanceof Error ? error.message : 'Unable to load monitor');
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
  }, [id, range]);

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

  if (notFound) {
    return <Navigate to="/" replace />;
  }

  if (loading && !monitor) {
    return (
      <div className="rounded-lg border border-dashed border-border bg-secondary p-12 text-center">
        <p className="text-lg font-semibold text-foreground">Loading monitor...</p>
      </div>
    );
  }

  if (error && !monitor) {
    return (
      <div className="rounded-lg bg-destructive/10 p-12 text-center">
        <p className="text-lg font-semibold text-destructive">Unable to load monitor</p>
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
              onClick={() => navigate(`/monitors/${monitor.id}/history`)}
              className="inline-flex items-center gap-2 rounded-lg border border-secondary bg-card px-3 py-1.5 text-sm font-medium text-primary transition-colors hover:border-border"
            >
              View history
              <ArrowRight className="h-4 w-4" />
            </button>
          </div>
        </div>
      </section>

      {error && (
        <div className="rounded-lg bg-destructive/10 p-4 text-sm text-destructive">{error}</div>
      )}

      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        <MetricCard label="Status" value={getStatusLabel(monitor.status)} hint="Current monitor state" icon={Zap} />
        <MetricCard
          label="Average response"
          value={averageMs !== null ? `${averageMs} ms` : 'No data'}
          hint={`From checks in the last ${range}`}
          icon={Clock3}
        />
        <MetricCard label="Checks" value={String(checks.length)} hint={`Completed in the last ${range}`} icon={FileText} />
        <MetricCard
          label="Interval"
          value={monitor.interval < 60 ? `${monitor.interval} s` : `${Math.round(monitor.interval / 60)} min`}
          hint="Scheduler cadence"
          icon={ServerCog}
        />
      </div>

      <div className="grid gap-6 xl:grid-cols-[1.2fr_0.8fr]">
        <Card>
          <CardHeader>
            <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
              <CardTitle>Response pattern</CardTitle>
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
                    {item}
                  </button>
                ))}
              </div>
            </div>
          </CardHeader>
          <CardContent>
            {chartData.length === 0 ? (
              <div className="rounded-lg border border-dashed border-border bg-secondary p-10 text-center text-sm text-placeholder">
                <p className="font-semibold text-muted-foreground">No checks in this range yet.</p>
                <p className="mt-2">
                  {monitor.status === 'pending'
                    ? 'This monitor is pending its first scheduled check.'
                    : 'Try a wider time range to see earlier results.'}
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
            <CardTitle>Config summary</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4 text-sm text-muted-foreground">
            {expected && (
              <div className="rounded-lg bg-secondary p-4">
                <p className="font-semibold text-foreground">HTTP expectations</p>
                {expected.status !== undefined && <p className="mt-2">Status: {expected.status}</p>}
                {expected.body_contains !== undefined && <p>Body contains: {expected.body_contains}</p>}
              </div>
            )}

            {steps.length > 0 && (
              <div className="rounded-lg bg-secondary p-4">
                <p className="font-semibold text-foreground">Browser scenario</p>
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

            <div className="rounded-lg bg-secondary p-4">
              <p className="font-semibold text-foreground">Last check</p>
              {lastCheck ? (
                <div className="mt-3 space-y-2 text-xs text-muted-foreground">
                  <div className="flex items-center gap-2">
                    <StatusBadge status={lastCheck.status} />
                    <span>{new Date(lastCheck.timestamp).toLocaleString()}</span>
                  </div>
                  <p>
                    {lastCheck.response_time_ms !== null
                      ? `Response time: ${lastCheck.response_time_ms} ms`
                      : 'No response time recorded'}
                  </p>
                  {lastCheck.error && <p className="font-medium text-destructive">{lastCheck.error}</p>}
                </div>
              ) : (
                <p className="mt-3 text-xs text-placeholder">No checks recorded yet.</p>
              )}
            </div>
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <FileText className="h-5 w-5 text-primary" />
            Recent checks
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          {checks.length === 0 ? (
            <div className="rounded-lg border border-dashed border-border bg-secondary p-8 text-center text-sm text-placeholder">
              No checks recorded in this range. New results appear here after the scheduler runs.
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
                    {check.response_time_ms !== null ? `${check.response_time_ms} ms` : check.error ?? 'No response'}
                  </p>
                </div>
                {check.error && <p className="mt-3 text-xs leading-5 text-destructive">{check.error}</p>}
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
