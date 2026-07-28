import { useMemo, useState } from 'react';
import { Link, useNavigate } from 'react-router';
import { ChevronLeft, FileSearch, Globe, Hourglass, Link2, MousePointerClick, Save, Type, WandSparkles } from 'lucide-react';
import { Button } from '../components/ui/Button';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/Card';
import { ApiError, createMonitor, type MonitorType } from '../api';
import { Input } from '../components/ui/Input';
import { cn } from '../utils/cn';
import { useTexts } from '../i18n';
import { useMeta } from '../meta-context';

type BrowserStepAction = 'goto' | 'click' | 'type' | 'assert_text' | 'wait_for' | 'assert_url';

type BuilderStep = {
  id: string;
  action: BrowserStepAction;
  label: string;
  selector?: string;
  value?: string;
  url?: string;
  expectedText?: string;
  contains?: string;
};

const stepIcons: Record<BrowserStepAction, typeof Globe> = {
  goto: Globe,
  click: MousePointerClick,
  type: Type,
  assert_text: FileSearch,
  wait_for: Hourglass,
  assert_url: Link2,
};

export default function AddMonitor() {
  const t = useTexts({
    ru: {
      newMonitor: 'Новый монитор',
      title: 'Собирайте в UI — конфиг всегда актуален',
      builderTitle: 'Конструктор мониторов',
      builderDescription:
        'Опишите быструю HTTP-проверку или полный браузерный сценарий. Сохранение также обновляет версию конфига.',
      typeHttp: 'HTTP',
      typeBrowser: 'Браузер',
      monitorName: 'Название монитора',
      monitorNamePlaceholder: 'Здоровье продакшен-API',
      targetUrl: 'Целевой URL',
      intervalSeconds: 'Интервал (секунды)',
      confirmationsLabel: 'Подтверждения (статус меняется после N проверок подряд)',
      renotifyLabel: 'Повторный алерт каждые N минут, пока монитор недоступен (0 = выкл)',
      expectedStatus: 'Ожидаемый статус',
      bodyContains: 'Тело ответа содержит',
      degradedAbove: 'Деградация свыше (мс)',
      scenarioBuilder: 'Конструктор сценария',
      supportedActions: 'Поддерживаемые действия: `goto`, `click`, `type`, `assert_text`, `wait_for`, `assert_url`.',
      stepLabels: {
        goto: 'Открыть страницу',
        click: 'Кликнуть по элементу',
        type: 'Ввести текст',
        assert_text: 'Проверить текст',
        wait_for: 'Дождаться элемента',
        assert_url: 'Проверить URL',
      } as Record<BrowserStepAction, string>,
      stepNumber: (n: number) => `Шаг ${n}`,
      remove: 'Удалить',
      stepLabel: 'Название шага',
      url: 'URL',
      selector: 'Селектор',
      value: 'Значение',
      urlContains: 'URL содержит',
      expectedText: 'Ожидаемый текст',
      selectorOptional: 'Селектор (необязательно)',
      savingNote: 'Сохранение вызывает API мониторов на бэкенде и обновляет сгенерированную версию конфига.',
      saveError: 'Не удалось сохранить монитор',
      cancel: 'Отмена',
      saveHttp: 'Сохранить HTTP-монитор',
      saveBrowser: 'Сохранить браузерный монитор',
    },
    en: {
      newMonitor: 'New monitor',
      title: 'Build from UI, keep config-ready',
      builderTitle: 'Monitor builder',
      builderDescription:
        'Model either a fast HTTP probe or a full browser scenario. Saving updates the config version too.',
      typeHttp: 'HTTP',
      typeBrowser: 'Browser',
      monitorName: 'Monitor name',
      monitorNamePlaceholder: 'Production API health',
      targetUrl: 'Target URL',
      intervalSeconds: 'Interval (seconds)',
      confirmationsLabel: 'Confirmations (status changes after N consecutive checks)',
      renotifyLabel: 'Re-alert every N minutes while down (0 = off)',
      expectedStatus: 'Expected status',
      bodyContains: 'Body contains',
      degradedAbove: 'Degraded above (ms)',
      scenarioBuilder: 'Scenario builder',
      supportedActions: 'Supported actions: `goto`, `click`, `type`, `assert_text`, `wait_for`, `assert_url`.',
      stepLabels: {
        goto: 'Open page',
        click: 'Click target',
        type: 'Type text',
        assert_text: 'Assert text',
        wait_for: 'Wait for element',
        assert_url: 'Assert URL',
      } as Record<BrowserStepAction, string>,
      stepNumber: (n: number) => `Step ${n}`,
      remove: 'Remove',
      stepLabel: 'Step label',
      url: 'URL',
      selector: 'Selector',
      value: 'Value',
      urlContains: 'URL contains',
      expectedText: 'Expected text',
      selectorOptional: 'Selector (optional)',
      savingNote: 'Saving calls the backend monitor API and updates the generated config version.',
      saveError: 'Unable to save monitor',
      cancel: 'Cancel',
      saveHttp: 'Save HTTP monitor',
      saveBrowser: 'Save browser monitor',
    },
  });
  const stepLabels = t.stepLabels;
  const navigate = useNavigate();
  // meta ещё не загружена — не мигаем переключателем, показываем как выключённый
  const browserEnabled = useMeta()?.browser_monitors_enabled ?? false;
  const [monitorType, setMonitorType] = useState<MonitorType>('http');
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState('');
  const [steps, setSteps] = useState<BuilderStep[]>(() => [
    { id: 'draft-1', action: 'goto', label: stepLabels.goto, url: 'https://example.com' },
  ]);

  const submitCopy = useMemo(
    () => (monitorType === 'http' ? t.saveHttp : t.saveBrowser),
    [monitorType, t.saveHttp, t.saveBrowser]
  );

  const addStep = (action: BrowserStepAction) => {
    setSteps((current) => [
      ...current,
      {
        id: crypto.randomUUID(),
        action,
        label: stepLabels[action],
        selector: '',
        value: '',
        url: '',
        expectedText: '',
        contains: '',
      },
    ]);
  };

  const updateStep = (id: string, key: keyof BuilderStep, value: string) => {
    setSteps((current) => current.map((step) => (step.id === id ? { ...step, [key]: value } : step)));
  };

  const removeStep = (id: string) => {
    setSteps((current) => current.filter((step) => step.id !== id));
  };

  const handleSubmit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setIsSaving(true);
    setError('');

    const formData = new FormData(event.currentTarget);
    const name = String(formData.get('name') ?? '').trim();
    const url = String(formData.get('url') ?? '').trim();
    const interval = Number(formData.get('interval') ?? 60);
    const expectedStatus = Number(formData.get('expectedStatus') ?? 200);
    const bodyContains = String(formData.get('bodyContains') ?? '').trim();
    const confirmations = Number(formData.get('confirmations') ?? 1);
    const renotifyMinutes = Number(formData.get('renotifyMinutes') ?? 0);
    const responseTimeMs = Number(formData.get('responseTimeMs') ?? 0);
    const slug = name
      .toLowerCase()
      .replace(/[^a-z0-9_.:-]+/g, '-')
      .replace(/^-+|-+$/g, '') || `monitor-${Date.now()}`;

    try {
      await createMonitor({
        id: slug,
        name,
        type: monitorType,
        url,
        interval,
        confirmations: confirmations > 1 ? confirmations : undefined,
        renotify_interval_minutes: renotifyMinutes > 0 ? renotifyMinutes : undefined,
        expected:
          monitorType === 'http'
            ? {
                status: expectedStatus,
                body_contains: bodyContains || undefined,
                response_time_ms: responseTimeMs > 0 ? responseTimeMs : undefined,
              }
            : undefined,
        steps:
          monitorType === 'browser'
            ? steps.map((step) => ({
                action: step.action,
                url: step.url,
                selector: step.selector,
                text: step.expectedText,
                value: step.value,
                contains: step.contains,
              }))
            : undefined,
      });
      navigate('/');
    } catch (error) {
      setError(error instanceof ApiError ? error.message : t.saveError);
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        <Link to="/" className="inline-flex h-10 w-10 items-center justify-center rounded-full bg-card text-muted-foreground shadow-card transition-colors hover:text-primary">
          <ChevronLeft className="h-5 w-5" />
        </Link>
        <div>
          <p className="text-sm font-semibold text-primary">{t.newMonitor}</p>
          <h1 className="text-2xl font-semibold leading-8 text-foreground">{t.title}</h1>
        </div>
      </div>

      <Card>
        <CardHeader className="border-b border-border">
          <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
            <div>
              <CardTitle>{t.builderTitle}</CardTitle>
              <p className="mt-2 text-sm text-muted-foreground">
                {t.builderDescription}
              </p>
            </div>
            <div className="flex rounded-xl bg-secondary p-1">
              <TypeToggle active={monitorType === 'http'} onClick={() => setMonitorType('http')}>
                {t.typeHttp}
              </TypeToggle>
              {/* сценарии могут быть выключены на инсталляции — тогда создание
                  всё равно вернёт 403, и переключатель показывал бы тупик */}
              {browserEnabled && (
                <TypeToggle active={monitorType === 'browser'} onClick={() => setMonitorType('browser')}>
                  {t.typeBrowser}
                </TypeToggle>
              )}
            </div>
          </div>
        </CardHeader>

        <CardContent className="p-6">
          <form onSubmit={handleSubmit} className="space-y-6">
            <div className="grid gap-4 md:grid-cols-2">
              <Input label={t.monitorName} name="name" placeholder={t.monitorNamePlaceholder} required />
              <Input label={t.targetUrl} name="url" placeholder="https://api.example.com/health" required />
              <Input label={t.intervalSeconds} name="interval" type="number" min={10} defaultValue={monitorType === 'http' ? 60 : 300} required />
              <Input
                label={t.confirmationsLabel}
                name="confirmations"
                type="number"
                min={1}
                max={10}
                defaultValue={1}
              />
              <Input
                label={t.renotifyLabel}
                name="renotifyMinutes"
                type="number"
                min={0}
                max={1440}
                defaultValue={0}
              />
            </div>

            {monitorType === 'http' ? (
              <div className="grid gap-4 lg:grid-cols-2">
                <Input label={t.expectedStatus} name="expectedStatus" type="number" placeholder="200" defaultValue="200" required />
                <Input label={t.bodyContains} name="bodyContains" placeholder="ok" defaultValue="ok" />
                <Input label={t.degradedAbove} name="responseTimeMs" type="number" min={1} placeholder="1500" />
              </div>
            ) : (
              <div className="space-y-5">
                <div className="rounded-lg bg-secondary p-4">
                  <div className="flex items-center justify-between gap-3">
                    <div>
                      <h3 className="text-base font-medium leading-6 text-foreground">{t.scenarioBuilder}</h3>
                      <p className="mt-1 text-sm text-muted-foreground">
                        {t.supportedActions}
                      </p>
                    </div>
                    <div className="flex flex-wrap gap-2">
                      {(['goto', 'click', 'type', 'assert_text', 'wait_for', 'assert_url'] as const).map((action) => {
                        const Icon = stepIcons[action];

                        return (
                          <Button
                            key={action}
                            type="button"
                            variant="outline"
                            size="sm"
                            className="gap-1.5"
                            onClick={() => addStep(action)}
                          >
                            <Icon className="h-3.5 w-3.5" />
                            {stepLabels[action]}
                          </Button>
                        );
                      })}
                    </div>
                  </div>
                </div>

                <div className="space-y-4">
                  {steps.map((step, index) => {
                    const Icon = stepIcons[step.action];

                    return (
                      <div key={step.id} className="rounded-lg border border-border bg-card p-4">
                        <div className="flex items-start justify-between gap-4">
                          <div className="flex items-center gap-3">
                            <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-accent text-primary">
                              <Icon className="h-5 w-5" />
                            </div>
                            <div>
                              <p className="text-sm font-semibold text-foreground">{t.stepNumber(index + 1)}</p>
                              <p className="text-sm text-placeholder">{step.action}</p>
                            </div>
                          </div>

                          {steps.length > 1 && (
                            <button
                              type="button"
                              onClick={() => removeStep(step.id)}
                              className="text-sm font-medium text-destructive hover:text-destructive/80"
                            >
                              {t.remove}
                            </button>
                          )}
                        </div>

                        <div className="mt-4 grid gap-4 md:grid-cols-2">
                          <Input
                            label={t.stepLabel}
                            value={step.label}
                            onChange={(event) => updateStep(step.id, 'label', event.target.value)}
                            required
                          />
                          {step.action === 'goto' && (
                            <Input
                              label={t.url}
                              value={step.url}
                              onChange={(event) => updateStep(step.id, 'url', event.target.value)}
                              required
                            />
                          )}
                          {step.action === 'click' && (
                            <Input
                              label={t.selector}
                              value={step.selector}
                              onChange={(event) => updateStep(step.id, 'selector', event.target.value)}
                              required
                            />
                          )}
                          {step.action === 'type' && (
                            <>
                              <Input
                                label={t.selector}
                                value={step.selector}
                                onChange={(event) => updateStep(step.id, 'selector', event.target.value)}
                                required
                              />
                              <Input
                                label={t.value}
                                value={step.value}
                                onChange={(event) => updateStep(step.id, 'value', event.target.value)}
                                required
                              />
                            </>
                          )}
                          {step.action === 'wait_for' && (
                            <Input
                              label={t.selector}
                              value={step.selector}
                              onChange={(event) => updateStep(step.id, 'selector', event.target.value)}
                              required
                            />
                          )}
                          {step.action === 'assert_url' && (
                            <Input
                              label={t.urlContains}
                              value={step.contains}
                              onChange={(event) => updateStep(step.id, 'contains', event.target.value)}
                              required
                            />
                          )}
                          {step.action === 'assert_text' && (
                            <>
                              <Input
                                label={t.expectedText}
                                value={step.expectedText}
                                onChange={(event) => updateStep(step.id, 'expectedText', event.target.value)}
                                required
                              />
                              <Input
                                label={t.selectorOptional}
                                value={step.selector}
                                onChange={(event) => updateStep(step.id, 'selector', event.target.value)}
                              />
                            </>
                          )}
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            )}

            <div className="rounded-lg bg-accent px-4 py-4 text-sm text-accent-foreground">
              <div className="flex items-start gap-3">
                <WandSparkles className="mt-0.5 h-4 w-4 shrink-0" />
                {t.savingNote}
              </div>
            </div>

            {error && (
              <div className="rounded-lg bg-destructive/10 px-4 py-4 text-sm text-destructive">
                {error}
              </div>
            )}

            <div className="flex flex-col gap-3 border-t border-border pt-5 sm:flex-row sm:justify-end">
              <Button type="button" variant="ghost" onClick={() => navigate(-1)}>
                {t.cancel}
              </Button>
              <Button type="submit" isLoading={isSaving}>
                <Save className="h-4 w-4" />
                {submitCopy}
              </Button>
            </div>
          </form>
        </CardContent>
      </Card>
    </div>
  );
}

function TypeToggle({
  active,
  onClick,
  children,
}: {
  active: boolean;
  onClick: () => void;
  children: string;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        'rounded-md px-3 py-1.5 text-sm font-medium transition-colors',
        active ? 'bg-card text-primary' : 'text-muted-foreground hover:text-primary'
      )}
    >
      {children}
    </button>
  );
}

