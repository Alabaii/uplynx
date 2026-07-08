import { useEffect, useMemo, useState } from 'react';
import { Link, Navigate, useParams } from 'react-router';
import { ArrowLeft, FileClock, ScrollText } from 'lucide-react';
import { Button } from '../components/ui/Button';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/Card';
import { StatusBadge } from '../components/StatusBadge';
import { ApiError, getHistory, getMonitor, type CheckResult, type Monitor, type MonitorStatus } from '../api';
import { cn } from '../utils/cn';

const ranges = ['1h', '24h', '7d', '30d'] as const;

export default function History() {
  const { id = '' } = useParams();
  const [monitor, setMonitor] = useState<Monitor | null>(null);
  const [checks, setChecks] = useState<CheckResult[]>([]);
  const [range, setRange] = useState<(typeof ranges)[number]>('24h');
  const [statusFilter, setStatusFilter] = useState<'all' | MonitorStatus>('all');
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
            setError(error instanceof Error ? error.message : 'Unable to load history');
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

  const filteredChecks = useMemo(
    () => checks.filter((check) => (statusFilter === 'all' ? true : check.status === statusFilter)),
    [checks, statusFilter]
  );

  const handleExport = () => {
    const blob = new Blob([JSON.stringify(filteredChecks, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `history-${id}-${range}.json`;
    link.click();
    URL.revokeObjectURL(url);
  };

  if (notFound) {
    return <Navigate to="/" replace />;
  }

  if (loading && !monitor) {
    return (
      <div className="rounded-lg border border-dashed border-border bg-secondary p-12 text-center">
        <p className="text-lg font-semibold text-foreground">Loading history...</p>
      </div>
    );
  }

  if (error && !monitor) {
    return (
      <div className="rounded-lg bg-destructive/10 p-12 text-center">
        <p className="text-lg font-semibold text-destructive">Unable to load history</p>
        <p className="mt-2 text-sm text-destructive">{error}</p>
      </div>
    );
  }

  if (!monitor) {
    return <Navigate to="/" replace />;
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <Link to={`/monitors/${monitor.id}`} className="inline-flex h-10 w-10 items-center justify-center rounded-full bg-card text-muted-foreground shadow-card transition-colors hover:text-primary">
            <ArrowLeft className="h-5 w-5" />
          </Link>
          <div>
            <p className="text-sm font-semibold text-primary">Monitor history</p>
            <h1 className="text-2xl font-semibold leading-8 text-foreground">{monitor.name}</h1>
          </div>
        </div>

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

      {error && (
        <div className="rounded-lg bg-destructive/10 p-4 text-sm text-destructive">{error}</div>
      )}

      <Card>
        <CardHeader className="gap-4 border-b border-border">
          <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
            <div>
              <CardTitle className="flex items-center gap-2">
                <ScrollText className="h-5 w-5 text-primary" />
                Check log
              </CardTitle>
              <p className="mt-2 text-sm text-muted-foreground">Current range: {range}. Filter recent results by state.</p>
            </div>

            <div className="flex flex-wrap gap-2">
              {(['all', 'up', 'degraded', 'down'] as const).map((item) => (
                <button
                  key={item}
                  type="button"
                  onClick={() => setStatusFilter(item)}
                  className={cn(
                    'rounded-lg px-3 py-1.5 text-[13px] leading-5 transition-colors',
                    statusFilter === item
                      ? 'bg-accent font-semibold text-primary'
                      : 'bg-secondary text-foreground hover:text-primary'
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
            <div className="rounded-lg border border-dashed border-border bg-secondary p-10 text-center text-sm text-placeholder">
              <p className="font-semibold text-muted-foreground">No checks in this range.</p>
              <p className="mt-2">
                {monitor.status === 'pending'
                  ? 'This monitor is pending its first scheduled check.'
                  : 'Try a wider time range or reset the status filter.'}
              </p>
            </div>
          ) : (
            filteredChecks.map((check) => (
              <div key={check.id} className="rounded-lg border border-border p-4">
                <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
                  <div className="space-y-3">
                    <div className="flex flex-wrap items-center gap-3">
                      <StatusBadge status={check.status} />
                      <p className="text-sm font-medium text-foreground">{new Date(check.timestamp).toLocaleString()}</p>
                    </div>

                    <div className="rounded-lg bg-secondary p-4 text-sm leading-5 text-muted-foreground">
                      {check.error ? <p className="font-medium text-destructive">{check.error}</p> : <p>Check completed successfully.</p>}
                      {check.details.failed_step && (
                        <p className="mt-2 text-xs text-muted-foreground">
                          Failed at step {check.details.failed_step.index}: {check.details.failed_step.action}{' '}
                          {check.details.failed_step.selector ?? check.details.failed_step.url ?? check.details.failed_step.contains ?? ''}
                        </p>
                      )}
                      {Object.keys(check.details).length > 0 && (
                        <div className="mt-3 space-y-1 font-mono text-xs text-placeholder">
                          {Object.entries(check.details)
                            .filter(([key]) => key !== 'screenshot' && key !== 'failed_step')
                            .map(([key, value]) => (
                              <div key={key}>
                                {key}: {typeof value === 'string' ? value : JSON.stringify(value)}
                              </div>
                            ))}
                        </div>
                      )}
                      {check.details.screenshot && (
                        <img
                          src={`data:image/jpeg;base64,${check.details.screenshot}`}
                          alt={`Screenshot of failed check at ${new Date(check.timestamp).toLocaleString()}`}
                          className="mt-3 max-h-40 rounded-lg border border-border"
                        />
                      )}
                    </div>
                  </div>

                  <div className="rounded-lg border border-border px-4 py-3 text-right">
                    <p className="text-[11px] font-semibold text-placeholder">Response</p>
                    <p className="mt-1 text-lg font-semibold text-foreground">
                      {check.response_time_ms !== null ? `${check.response_time_ms} ms` : 'No response'}
                    </p>
                  </div>
                </div>
              </div>
            ))
          )}
        </CardContent>
      </Card>

      <Card>
        <CardContent className="flex flex-col gap-4 p-6 lg:flex-row lg:items-center lg:justify-between">
          <div>
            <p className="text-sm font-semibold text-foreground">Export history</p>
            <p className="mt-2 text-sm leading-5 text-muted-foreground">
              Download the currently filtered checks as a JSON file for offline analysis.
            </p>
          </div>
          <Button variant="outline" onClick={handleExport} disabled={filteredChecks.length === 0}>
            <FileClock className="h-4 w-4" />
            Export JSON
          </Button>
        </CardContent>
      </Card>
    </div>
  );
}
