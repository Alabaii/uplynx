import { useCallback, useEffect, useState } from 'react';
import { useParams } from 'react-router';
import { Activity, AlertTriangle, CheckCircle2, XCircle } from 'lucide-react';
import { StatusBadge } from '../components/StatusBadge';
import { ApiError, getPublicStatus, type PublicStatus, type PublicStatusOverall } from '../api';
import { cn } from '../utils/cn';
import { formatRelativeTime } from '../utils/time';
import { useTexts } from '../i18n';

const REFRESH_INTERVAL_MS = 60_000;

const overallClasses: Record<PublicStatusOverall, string> = {
  operational: 'bg-accent text-primary',
  degraded: 'bg-status-degraded/15 text-status-degraded',
  down: 'bg-status-down/10 text-status-down',
};

const overallIcons: Record<PublicStatusOverall, typeof CheckCircle2> = {
  operational: CheckCircle2,
  degraded: AlertTriangle,
  down: XCircle,
};

function NotFoundScreen() {
  const t = useTexts({
    ru: {
      title: 'Статус-страница не найдена',
      description: 'Эта статус-страница не существует или недоступна публично.',
      poweredBy: 'Работает на PWA Monitor',
    },
    en: {
      title: 'Status page not found',
      description: 'This status page does not exist or is not publicly available.',
      poweredBy: 'Powered by PWA Monitor',
    },
  });

  return (
    <div className="mx-auto flex min-h-screen max-w-2xl flex-col items-center justify-center px-4 text-center">
      <div className="w-full rounded-lg bg-card p-10 shadow-card">
        <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-lg bg-secondary">
          <Activity className="h-6 w-6 text-placeholder" />
        </div>
        <h1 className="mt-6 text-2xl font-semibold text-foreground">{t.title}</h1>
        <p className="mt-3 text-sm text-muted-foreground">{t.description}</p>
      </div>
      <p className="mt-8 text-xs text-placeholder">{t.poweredBy}</p>
    </div>
  );
}

export default function StatusPage() {
  const t = useTexts({
    ru: {
      overall: {
        operational: 'Все системы работают',
        degraded: 'Производительность снижена',
        down: 'Сбой в работе сервиса',
      },
      statusLabel: 'Статус',
      updated: (time: string) => `Обновлено ${time}`,
      loadError: 'Не удалось загрузить статус. Повторим автоматически.',
      loading: 'Загрузка статуса...',
      noMonitors: 'Мониторы ещё не опубликованы.',
      maintenance: 'Обслуживание',
      uptime24h: 'Аптайм за 24 ч:',
      lastCheck: (time: string) => `Последняя проверка: ${time}`,
      poweredBy: 'Работает на PWA Monitor',
    },
    en: {
      overall: {
        operational: 'All systems operational',
        degraded: 'Degraded performance',
        down: 'Service disruption',
      },
      statusLabel: 'Status',
      updated: (time: string) => `Updated ${time}`,
      loadError: 'Unable to load status. Retrying automatically.',
      loading: 'Loading status...',
      noMonitors: 'No monitors are published yet.',
      maintenance: 'Maintenance',
      uptime24h: 'Uptime 24h:',
      lastCheck: (time: string) => `Last check: ${time}`,
      poweredBy: 'Powered by PWA Monitor',
    },
  });
  const { slug } = useParams<{ slug: string }>();
  const [data, setData] = useState<PublicStatus | null>(null);
  const [notFound, setNotFound] = useState(false);
  const [error, setError] = useState('');

  const load = useCallback(() => {
    if (!slug) {
      setNotFound(true);
      return;
    }

    getPublicStatus(slug)
      .then((status) => {
        setData(status);
        setNotFound(false);
        setError('');
      })
      .catch((error) => {
        if (error instanceof ApiError && error.status === 404) {
          setNotFound(true);
        } else {
          setError(t.loadError);
        }
      });
  }, [slug]);

  useEffect(() => {
    load();
    const timer = window.setInterval(load, REFRESH_INTERVAL_MS);

    return () => {
      window.clearInterval(timer);
    };
  }, [load]);

  if (notFound) {
    return <NotFoundScreen />;
  }

  if (!data) {
    return (
      <div className="mx-auto flex min-h-screen max-w-2xl items-center justify-center px-4">
        <div className="w-full rounded-lg bg-card p-10 text-center text-sm text-placeholder shadow-card">
          {error || t.loading}
        </div>
      </div>
    );
  }

  const OverallIcon = overallIcons[data.overall];

  return (
    <div className="min-h-screen bg-background px-4 py-10 text-foreground">
      <div className="mx-auto max-w-2xl space-y-6">
        <header className="rounded-lg bg-card p-6 shadow-card">
          <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <p className="text-sm font-semibold text-primary">{t.statusLabel}</p>
              <h1 className="mt-1 text-2xl font-semibold leading-8">{data.organization}</h1>
            </div>
            <span
              className={cn(
                'inline-flex shrink-0 items-center gap-2 rounded-lg px-3 py-1.5 text-sm font-semibold',
                overallClasses[data.overall]
              )}
            >
              <OverallIcon className="h-4 w-4" />
              {t.overall[data.overall]}
            </span>
          </div>
          <p className="mt-4 text-xs text-placeholder">{t.updated(formatRelativeTime(data.updated_at))}</p>
        </header>

        {error && <div className="rounded-lg bg-destructive/10 p-4 text-sm text-destructive">{error}</div>}

        <section className="space-y-3">
          {data.monitors.length === 0 ? (
            <div className="rounded-lg bg-card p-6 text-sm text-muted-foreground shadow-card">
              {t.noMonitors}
            </div>
          ) : (
            data.monitors.map((monitor, index) => (
              <div
                // slug наружу не отдаём, а имена могут совпадать — ключ по индексу
                key={index}
                className="flex flex-col gap-3 rounded-lg bg-card p-4 shadow-card sm:flex-row sm:items-center sm:justify-between"
              >
                <div className="flex min-w-0 items-center gap-3">
                  <p className="truncate text-sm font-semibold text-foreground">{monitor.name}</p>
                  {monitor.in_maintenance ? (
                    <span className="inline-flex items-center rounded-lg bg-secondary px-2.5 py-1 text-xs font-semibold text-muted-foreground">
                      {t.maintenance}
                    </span>
                  ) : (
                    <StatusBadge status={monitor.status} />
                  )}
                </div>
                <div className="flex shrink-0 items-center gap-4 text-xs text-muted-foreground">
                  <span>
                    {t.uptime24h}{' '}
                    <span className="font-semibold text-foreground">
                      {monitor.uptime_pct === null ? '—' : `${monitor.uptime_pct}%`}
                    </span>
                  </span>
                  <span>{t.lastCheck(formatRelativeTime(monitor.last_check_at))}</span>
                </div>
              </div>
            ))
          )}
        </section>

        <footer className="pb-4 text-center text-xs text-placeholder">{t.poweredBy}</footer>
      </div>
    </div>
  );
}
