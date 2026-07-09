import { useEffect, useMemo, useState } from 'react';
import { Link, Navigate, useParams } from 'react-router';
import { ArrowLeft, FileClock, ScrollText } from 'lucide-react';
import { Button } from '../components/ui/Button';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/Card';
import { StatusBadge } from '../components/StatusBadge';
import { ApiError, getHistory, getMonitor, type CheckResult, type Monitor, type MonitorStatus } from '../api';
import { useTexts } from '../i18n';
import { cn } from '../utils/cn';

const ranges = ['1h', '24h', '7d', '30d'] as const;

export default function History() {
  const t = useTexts({
    ru: {
      loadError: 'Не удалось загрузить историю',
      loading: 'Загрузка истории...',
      monitorHistory: 'История монитора',
      rangeLabels: { '1h': '1 ч', '24h': '24 ч', '7d': '7 дн', '30d': '30 дн' } as Record<(typeof ranges)[number], string>,
      checkLog: 'Журнал проверок',
      currentRange: (range: string) => `Текущий диапазон: ${range}. Фильтруйте последние результаты по состоянию.`,
      statusLabels: { all: 'Все', up: 'работает', degraded: 'деградация', down: 'недоступен' } as Record<'all' | 'up' | 'degraded' | 'down', string>,
      noChecks: 'Нет проверок за этот период.',
      pendingHint: 'Монитор ожидает первую запланированную проверку.',
      widenHint: 'Попробуйте расширить диапазон или сбросить фильтр статуса.',
      checkOk: 'Проверка выполнена успешно.',
      failedAtStep: (index: number, action: string) => `Ошибка на шаге ${index}: ${action}`,
      response: 'Ответ',
      responseMs: (ms: number) => `${ms} мс`,
      noResponse: 'Нет ответа',
      exportTitle: 'Экспорт истории',
      exportDescription: 'Скачайте отфильтрованные проверки в файле JSON для офлайн-анализа.',
      exportButton: 'Экспорт JSON',
    },
    en: {
      loadError: 'Unable to load history',
      loading: 'Loading history...',
      monitorHistory: 'Monitor history',
      rangeLabels: { '1h': '1h', '24h': '24h', '7d': '7d', '30d': '30d' } as Record<(typeof ranges)[number], string>,
      checkLog: 'Check log',
      currentRange: (range: string) => `Current range: ${range}. Filter recent results by state.`,
      statusLabels: { all: 'All', up: 'up', degraded: 'degraded', down: 'down' } as Record<'all' | 'up' | 'degraded' | 'down', string>,
      noChecks: 'No checks in this range.',
      pendingHint: 'This monitor is pending its first scheduled check.',
      widenHint: 'Try a wider time range or reset the status filter.',
      checkOk: 'Check completed successfully.',
      failedAtStep: (index: number, action: string) => `Failed at step ${index}: ${action}`,
      response: 'Response',
      responseMs: (ms: number) => `${ms} ms`,
      noResponse: 'No response',
      exportTitle: 'Export history',
      exportDescription: 'Download the currently filtered checks as a JSON file for offline analysis.',
      exportButton: 'Export JSON',
    },
  });
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
            setError(error instanceof Error ? error.message : t.loadError);
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
        <p className="text-lg font-semibold text-foreground">{t.loading}</p>
      </div>
    );
  }

  if (error && !monitor) {
    return (
      <div className="rounded-lg bg-destructive/10 p-12 text-center">
        <p className="text-lg font-semibold text-destructive">{t.loadError}</p>
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
            <p className="text-sm font-semibold text-primary">{t.monitorHistory}</p>
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
              {t.rangeLabels[item]}
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
                {t.checkLog}
              </CardTitle>
              <p className="mt-2 text-sm text-muted-foreground">{t.currentRange(t.rangeLabels[range])}</p>
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
                  {t.statusLabels[item]}
                </button>
              ))}
            </div>
          </div>
        </CardHeader>

        <CardContent className="space-y-4 p-4 md:p-6">
          {filteredChecks.length === 0 ? (
            <div className="rounded-lg border border-dashed border-border bg-secondary p-10 text-center text-sm text-placeholder">
              <p className="font-semibold text-muted-foreground">{t.noChecks}</p>
              <p className="mt-2">
                {monitor.status === 'pending' ? t.pendingHint : t.widenHint}
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
                      {check.error ? <p className="font-medium text-destructive">{check.error}</p> : <p>{t.checkOk}</p>}
                      {check.details.failed_step && (
                        <p className="mt-2 text-xs text-muted-foreground">
                          {t.failedAtStep(check.details.failed_step.index, check.details.failed_step.action)}{' '}
                          {check.details.failed_step.selector ?? check.details.failed_step.url ?? check.details.failed_step.contains ?? ''}
                        </p>
                      )}
                      {Object.keys(check.details).length > 0 && (
                        <div className="mt-3 space-y-1 font-mono text-xs text-placeholder">
                          {Object.entries(check.details)
                            // screenshot — устаревшее поле старых записей (base64), в UI не показываем
                            .filter(([key]) => key !== 'screenshot' && key !== 'failed_step')
                            .map(([key, value]) => (
                              <div key={key}>
                                {key}: {typeof value === 'string' ? value : JSON.stringify(value)}
                              </div>
                            ))}
                        </div>
                      )}
                    </div>
                  </div>

                  <div className="rounded-lg border border-border px-4 py-3 text-right">
                    <p className="text-[11px] font-semibold text-placeholder">{t.response}</p>
                    <p className="mt-1 text-lg font-semibold text-foreground">
                      {check.response_time_ms !== null ? t.responseMs(check.response_time_ms) : t.noResponse}
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
            <p className="text-sm font-semibold text-foreground">{t.exportTitle}</p>
            <p className="mt-2 text-sm leading-5 text-muted-foreground">
              {t.exportDescription}
            </p>
          </div>
          <Button variant="outline" onClick={handleExport} disabled={filteredChecks.length === 0}>
            <FileClock className="h-4 w-4" />
            {t.exportButton}
          </Button>
        </CardContent>
      </Card>
    </div>
  );
}
