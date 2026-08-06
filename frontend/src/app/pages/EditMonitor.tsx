import { useEffect, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router';
import { ChevronLeft, Save } from 'lucide-react';
import { Button } from '../components/ui/Button';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/Card';
import { ApiError, getMonitor, updateMonitor, type Monitor } from '../api';
import { Input } from '../components/ui/Input';
import { useTexts } from '../i18n';

export default function EditMonitor() {
  const t = useTexts({
    ru: {
      editMonitor: 'Редактирование',
      title: 'Изменить параметры монитора',
      formTitle: 'Параметры',
      formDescription:
        'Тип монитора менять нельзя — для этого создайте новый. Сохранение обновляет версию конфига.',
      monitorName: 'Название монитора',
      targetUrl: 'Целевой URL',
      intervalSeconds: 'Интервал (секунды)',
      confirmationsLabel: 'Подтверждения (статус меняется после N проверок подряд)',
      renotifyLabel: 'Повторный алерт каждые N минут, пока монитор недоступен (0 = выкл)',
      expectedStatus: 'Ожидаемый статус',
      bodyContains: 'Тело ответа содержит',
      degradedAbove: 'Деградация свыше (мс)',
      enabledLabel: 'Монитор включён',
      enabledHint: 'Выключенный монитор не проверяется, а открытый инцидент по нему закрывается.',
      scenarioNote:
        'Шаги браузерного сценария здесь не редактируются — они остаются прежними.',
      loading: 'Загрузка монитора…',
      notFound: 'Монитор не найден',
      loadError: 'Не удалось загрузить монитор',
      saveError: 'Не удалось сохранить монитор',
      cancel: 'Отмена',
      save: 'Сохранить изменения',
    },
    en: {
      editMonitor: 'Editing',
      title: 'Change monitor settings',
      formTitle: 'Settings',
      formDescription:
        'Monitor type cannot be changed — create a new monitor instead. Saving updates the config version.',
      monitorName: 'Monitor name',
      targetUrl: 'Target URL',
      intervalSeconds: 'Interval (seconds)',
      confirmationsLabel: 'Confirmations (status changes after N consecutive checks)',
      renotifyLabel: 'Re-alert every N minutes while down (0 = off)',
      expectedStatus: 'Expected status',
      bodyContains: 'Body contains',
      degradedAbove: 'Degraded above (ms)',
      enabledLabel: 'Monitor enabled',
      enabledHint: 'A disabled monitor is not checked, and its open incident gets resolved.',
      scenarioNote: 'Browser scenario steps are not edited here — they stay as they are.',
      loading: 'Loading monitor…',
      notFound: 'Monitor not found',
      loadError: 'Unable to load monitor',
      saveError: 'Unable to save monitor',
      cancel: 'Cancel',
      save: 'Save changes',
    },
  });
  const { id = '' } = useParams();
  const navigate = useNavigate();
  const [monitor, setMonitor] = useState<Monitor | null>(null);
  const [loading, setLoading] = useState(true);
  const [notFound, setNotFound] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    let ignore = false;

    setLoading(true);
    getMonitor(id)
      .then((data) => {
        if (!ignore) {
          setMonitor(data);
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
  }, [id]);

  const handleSubmit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!monitor) {
      return;
    }

    const form = new FormData(event.currentTarget);
    const interval = Number(form.get('interval'));
    const confirmations = Number(form.get('confirmations') ?? 1);
    const renotifyMinutes = Number(form.get('renotifyMinutes') ?? 0);
    const url = String(form.get('url') ?? '').trim();

    setIsSaving(true);
    setError('');
    try {
      await updateMonitor(id, {
        name: String(form.get('name') ?? '').trim(),
        // у браузерного монитора адрес задают шаги, поле формы не показывается
        url: monitor.type === 'http' ? url : undefined,
        interval,
        confirmations,
        // ноль в поле значит «выключено», но схема принимает только >= 1 —
        // сброс настройки бэкенд понимает как null
        renotify_interval_minutes: renotifyMinutes > 0 ? renotifyMinutes : null,
        enabled: form.get('enabled') === 'on',
        expected:
          monitor.type === 'http'
            ? {
                status: Number(form.get('expectedStatus')),
                body_contains: String(form.get('bodyContains') ?? '').trim() || undefined,
                response_time_ms: Number(form.get('responseTimeMs')) || undefined,
              }
            : undefined,
      });
      navigate(`/monitors/${encodeURIComponent(id)}`);
    } catch (error) {
      setError(error instanceof ApiError ? error.message : t.saveError);
      setIsSaving(false);
    }
  };

  if (loading) {
    return <p className="text-sm text-muted-foreground">{t.loading}</p>;
  }

  if (notFound || !monitor) {
    return <p className="text-sm text-muted-foreground">{t.notFound}</p>;
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        <Link
          to={`/monitors/${encodeURIComponent(id)}`}
          className="inline-flex h-10 w-10 items-center justify-center rounded-full bg-card text-muted-foreground shadow-card transition-colors hover:text-primary"
        >
          <ChevronLeft className="h-5 w-5" />
        </Link>
        <div>
          <p className="text-sm font-semibold text-primary">{t.editMonitor}</p>
          <h1 className="text-2xl font-semibold leading-8 text-foreground">{t.title}</h1>
        </div>
      </div>

      <Card>
        <CardHeader className="border-b border-border">
          <CardTitle>{t.formTitle}</CardTitle>
          <p className="mt-2 text-sm text-muted-foreground">{t.formDescription}</p>
        </CardHeader>

        <CardContent className="p-6">
          <form onSubmit={handleSubmit} className="space-y-6">
            <div className="grid gap-4 md:grid-cols-2">
              <Input label={t.monitorName} name="name" defaultValue={monitor.name} required />
              {monitor.type === 'http' && (
                <Input label={t.targetUrl} name="url" defaultValue={monitor.url ?? ''} required />
              )}
              <Input
                label={t.intervalSeconds}
                name="interval"
                type="number"
                min={10}
                defaultValue={monitor.interval}
                required
              />
              <Input
                label={t.confirmationsLabel}
                name="confirmations"
                type="number"
                min={1}
                max={10}
                defaultValue={monitor.confirmations ?? 1}
              />
              <Input
                label={t.renotifyLabel}
                name="renotifyMinutes"
                type="number"
                min={0}
                max={1440}
                defaultValue={monitor.config.renotify_interval_minutes ?? 0}
              />
            </div>

            {monitor.type === 'http' ? (
              <div className="grid gap-4 lg:grid-cols-2">
                <Input
                  label={t.expectedStatus}
                  name="expectedStatus"
                  type="number"
                  defaultValue={monitor.config.expected?.status ?? 200}
                  required
                />
                <Input
                  label={t.bodyContains}
                  name="bodyContains"
                  defaultValue={monitor.config.expected?.body_contains ?? ''}
                />
                <Input
                  label={t.degradedAbove}
                  name="responseTimeMs"
                  type="number"
                  min={1}
                  defaultValue={monitor.config.expected?.response_time_ms ?? ''}
                />
              </div>
            ) : (
              <p className="rounded-lg bg-secondary p-4 text-sm text-muted-foreground">{t.scenarioNote}</p>
            )}

            <label className="flex items-start gap-3 rounded-lg bg-secondary p-4">
              <input
                type="checkbox"
                name="enabled"
                defaultChecked={monitor.enabled}
                className="mt-0.5 h-4 w-4 rounded border-border text-primary"
              />
              <span>
                <span className="block text-sm font-medium text-foreground">{t.enabledLabel}</span>
                <span className="mt-1 block text-sm text-muted-foreground">{t.enabledHint}</span>
              </span>
            </label>

            {error && <p className="text-sm text-destructive">{error}</p>}

            <div className="flex flex-wrap justify-end gap-3">
              <Button
                type="button"
                variant="secondary"
                onClick={() => navigate(`/monitors/${encodeURIComponent(id)}`)}
              >
                {t.cancel}
              </Button>
              <Button type="submit" disabled={isSaving}>
                <Save className="h-4 w-4" />
                {t.save}
              </Button>
            </div>
          </form>
        </CardContent>
      </Card>
    </div>
  );
}
