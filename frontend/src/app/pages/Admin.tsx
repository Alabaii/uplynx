import { useCallback, useEffect, useState } from 'react';
import {
  Activity,
  AlertTriangle,
  Building2,
  CheckCircle2,
  Gauge,
  RefreshCw,
  Save,
  ShieldCheck,
  Users,
} from 'lucide-react';
import { Button } from '../components/ui/Button';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/Card';
import { Input } from '../components/ui/Input';
import {
  ApiError,
  getAdminOverview,
  getMe,
  listAdminOrgs,
  listPlans,
  setOrgPlan,
  updatePlan,
  type AdminOrg,
  type AdminOverview,
  type Plan,
} from '../api';
import { cn } from '../utils/cn';
import { plural, useTexts } from '../i18n';

type TabId = 'overview' | 'plans' | 'organizations';

const selectClasses =
  'h-9 w-full rounded-lg border border-input bg-input-background px-2 text-sm text-foreground transition-colors hover:border-input-border-hover focus:border-input-border-hover focus:outline-none focus:ring-2 focus:ring-ring/20';

function StatCard({ label, value, hint, alert }: { label: string; value: string; hint?: string; alert?: boolean }) {
  return (
    <div className="rounded-lg bg-card p-4 shadow-card">
      <p className="text-xs text-placeholder">{label}</p>
      <p className={cn('mt-1 text-2xl font-semibold leading-8', alert ? 'text-status-down' : 'text-foreground')}>
        {value}
      </p>
      {hint && <p className="mt-0.5 text-xs text-muted-foreground">{hint}</p>}
    </div>
  );
}

function OverviewTab() {
  const t = useTexts({
    ru: {
      loadError: 'Не удалось загрузить статистику платформы',
      loading: 'Загрузка статистики платформы...',
      noHeartbeat: 'нет heartbeat',
      secondsAgo: (s: number) => `${s} с назад`,
      subtitle: 'Актуальные показатели платформы по всем организациям.',
      refresh: 'Обновить',
      users: 'Пользователи',
      organizations: 'Организации',
      monitors: 'Мониторы',
      monitorsHint: (enabled: number, browser: number) => `${enabled} включено · ${browser} браузерных`,
      checks24h: 'Проверки (24 ч)',
      openIncidents: 'Открытые инциденты',
      schedulerHeartbeat: 'Heartbeat шедулера',
      monitorsOverdue: (n: number) =>
        `${n} ${plural(n, ['монитор просрочен', 'монитора просрочены', 'мониторов просрочено'])}`,
      onSchedule: 'по расписанию',
      queues: 'Очереди',
      rabbitUnreachable: 'RabbitMQ недоступен — глубина очередей неизвестна.',
      dlq: 'очередь недоставленных (DLQ)',
      workQueue: 'рабочая очередь',
    },
    en: {
      loadError: 'Unable to load platform stats',
      loading: 'Loading platform stats...',
      noHeartbeat: 'no heartbeat',
      secondsAgo: (s: number) => `${s}s ago`,
      subtitle: 'Live platform totals across every organization.',
      refresh: 'Refresh',
      users: 'Users',
      organizations: 'Organizations',
      monitors: 'Monitors',
      monitorsHint: (enabled: number, browser: number) => `${enabled} enabled · ${browser} browser`,
      checks24h: 'Checks (24h)',
      openIncidents: 'Open incidents',
      schedulerHeartbeat: 'Scheduler heartbeat',
      monitorsOverdue: (n: number) => `${n} monitors overdue`,
      onSchedule: 'on schedule',
      queues: 'Queues',
      rabbitUnreachable: 'RabbitMQ is unreachable — queue depths unavailable.',
      dlq: 'dead-letter queue',
      workQueue: 'work queue',
    },
  });
  const [data, setData] = useState<AdminOverview | null>(null);
  const [error, setError] = useState('');
  const [isLoading, setIsLoading] = useState(false);

  const load = useCallback(() => {
    setIsLoading(true);
    getAdminOverview()
      .then((overview) => {
        setData(overview);
        setError('');
      })
      .catch((err) => setError(err instanceof ApiError ? err.message : t.loadError))
      .finally(() => setIsLoading(false));
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  if (error) {
    return <div className="rounded-lg bg-destructive/10 p-4 text-sm text-destructive">{error}</div>;
  }
  if (!data) {
    return <div className="rounded-lg bg-secondary p-4 text-sm text-muted-foreground">{t.loading}</div>;
  }

  const scheduler = data.scheduler;
  const schedulerValue =
    scheduler.beat_age_seconds === null ? t.noHeartbeat : t.secondsAgo(scheduler.beat_age_seconds);

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <p className="text-sm text-muted-foreground">{t.subtitle}</p>
        <Button variant="outline" size="sm" onClick={load} isLoading={isLoading}>
          <RefreshCw className="h-4 w-4" />
          {t.refresh}
        </Button>
      </div>

      <div className="grid grid-cols-2 gap-4 md:grid-cols-3 xl:grid-cols-4">
        <StatCard label={t.users} value={String(data.users_total)} />
        <StatCard label={t.organizations} value={String(data.orgs_total)} />
        <StatCard
          label={t.monitors}
          value={String(data.monitors_total)}
          hint={t.monitorsHint(data.monitors_enabled, data.monitors_browser)}
        />
        <StatCard label={t.checks24h} value={data.checks_24h.toLocaleString()} />
        <StatCard label={t.openIncidents} value={String(data.incidents_open)} alert={data.incidents_open > 0} />
        <StatCard
          label={t.schedulerHeartbeat}
          value={schedulerValue}
          hint={scheduler.overdue_monitors > 0 ? t.monitorsOverdue(scheduler.overdue_monitors) : t.onSchedule}
          alert={scheduler.stale}
        />
      </div>

      <Card>
        <CardHeader className="border-b border-border">
          <CardTitle className="flex items-center gap-2">
            <Gauge className="h-5 w-5 text-primary" />
            {t.queues}
          </CardTitle>
        </CardHeader>
        <CardContent className="p-6">
          {data.queues === null ? (
            <div className="flex items-center gap-2 rounded-lg bg-destructive/10 p-4 text-sm text-destructive">
              <AlertTriangle className="h-4 w-4" />
              {t.rabbitUnreachable}
            </div>
          ) : (
            <div className="grid gap-3 sm:grid-cols-2">
              {data.queues.map((queue) => {
                const isDead = queue.name.endsWith('.dlq');
                const troubling = isDead && queue.depth > 0;
                return (
                  <div
                    key={queue.name}
                    className={cn(
                      'flex items-center justify-between rounded-lg border border-border p-4',
                      troubling && 'border-status-down/40 bg-destructive/5'
                    )}
                  >
                    <div>
                      <p className="text-sm font-semibold text-foreground">{queue.name}</p>
                      <p className="text-xs text-placeholder">{isDead ? t.dlq : t.workQueue}</p>
                    </div>
                    <span
                      className={cn(
                        'text-xl font-semibold',
                        troubling ? 'text-status-down' : 'text-foreground'
                      )}
                    >
                      {queue.depth}
                    </span>
                  </div>
                );
              })}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

type PlanFormState = {
  price: string;
  discount: string;
  maxMonitors: string;
  minInterval: number;
  maxBrowser: string;
  browserMinInterval: number;
  members: string;
  unlimitedMembers: boolean;
  retention: number;
};

function formStateFromPlan(plan: Plan): PlanFormState {
  return {
    price: (plan.price_monthly_kopeks / 100).toString(),
    discount: plan.annual_discount_pct.toString(),
    maxMonitors: plan.max_monitors.toString(),
    minInterval: plan.min_interval_seconds,
    maxBrowser: plan.max_browser_monitors.toString(),
    browserMinInterval: plan.browser_min_interval_seconds,
    members: plan.max_members === null ? '' : plan.max_members.toString(),
    unlimitedMembers: plan.max_members === null,
    retention: plan.retention_days,
  };
}

function PlanCard({ plan, onSaved }: { plan: Plan; onSaved: (plan: Plan) => void }) {
  const t = useTexts({
    ru: {
      intervalOptions: [
        { value: 10, label: '10 секунд' },
        { value: 30, label: '30 секунд' },
        { value: 60, label: '1 минута' },
        { value: 300, label: '5 минут' },
        { value: 900, label: '15 минут' },
      ],
      retentionOptions: [
        { value: 30, label: '30 дней' },
        { value: 90, label: '90 дней' },
        { value: 365, label: '1 год' },
      ],
      saved: 'Сохранено.',
      saveError: 'Не удалось сохранить тариф',
      priceLabel: 'Цена, ₽/мес',
      discountLabel: 'Годовая скидка, %',
      annualHint: (price: string) => `≈ ${price} ₽/мес при оплате за год`,
      monitorsLabel: 'Мониторы',
      browserMonitorsLabel: 'Браузерные мониторы',
      minIntervalLabel: 'Мин. интервал',
      browserMinIntervalLabel: 'Мин. интервал (браузерные)',
      teamMembersLabel: 'Участники команды',
      unlimited: 'Без ограничений',
      retentionLabel: 'Хранение истории',
      save: (name: string) => `Сохранить ${name}`,
    },
    en: {
      intervalOptions: [
        { value: 10, label: '10 seconds' },
        { value: 30, label: '30 seconds' },
        { value: 60, label: '1 minute' },
        { value: 300, label: '5 minutes' },
        { value: 900, label: '15 minutes' },
      ],
      retentionOptions: [
        { value: 30, label: '30 days' },
        { value: 90, label: '90 days' },
        { value: 365, label: '1 year' },
      ],
      saved: 'Saved.',
      saveError: 'Unable to save plan',
      priceLabel: 'Price, ₽/month',
      discountLabel: 'Annual discount, %',
      annualHint: (price: string) => `≈ ${price} ₽/month billed annually`,
      monitorsLabel: 'Monitors',
      browserMonitorsLabel: 'Browser monitors',
      minIntervalLabel: 'Min interval',
      browserMinIntervalLabel: 'Browser min interval',
      teamMembersLabel: 'Team members',
      unlimited: 'Unlimited',
      retentionLabel: 'History retention',
      save: (name: string) => `Save ${name}`,
    },
  });
  const [form, setForm] = useState<PlanFormState>(() => formStateFromPlan(plan));
  const [isSaving, setIsSaving] = useState(false);
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');

  const set = <K extends keyof PlanFormState>(key: K, value: PlanFormState[K]) => {
    setForm((current) => ({ ...current, [key]: value }));
    setMessage('');
  };

  const priceValue = Number.parseFloat(form.price);
  const discountValue = Number.parseInt(form.discount, 10);
  const annualMonthly =
    Number.isFinite(priceValue) && Number.isFinite(discountValue)
      ? priceValue * (1 - discountValue / 100)
      : null;

  const handleSave = async () => {
    setIsSaving(true);
    setMessage('');
    setError('');
    try {
      const updated = await updatePlan(plan.slug, {
        price_monthly_kopeks: Math.round(Number.parseFloat(form.price || '0') * 100),
        annual_discount_pct: Number.parseInt(form.discount || '0', 10),
        max_monitors: Number.parseInt(form.maxMonitors || '1', 10),
        min_interval_seconds: form.minInterval,
        max_browser_monitors: Number.parseInt(form.maxBrowser || '0', 10),
        browser_min_interval_seconds: form.browserMinInterval,
        retention_days: form.retention,
        ...(form.unlimitedMembers
          ? { unlimited_members: true }
          : { max_members: Number.parseInt(form.members || '1', 10) }),
      });
      onSaved(updated);
      setForm(formStateFromPlan(updated));
      setMessage(t.saved);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : t.saveError);
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <Card>
      <CardHeader className="border-b border-border">
        <div className="flex items-center justify-between">
          <CardTitle>{plan.name}</CardTitle>
          <span className="rounded-lg bg-secondary px-2.5 py-1 text-xs font-semibold text-muted-foreground">
            {plan.slug}
          </span>
        </div>
      </CardHeader>
      <CardContent className="space-y-4 p-6">
        <div className="grid grid-cols-2 gap-3">
          <Input
            label={t.priceLabel}
            type="number"
            min="0"
            step="1"
            value={form.price}
            onChange={(event) => set('price', event.target.value)}
          />
          <Input
            label={t.discountLabel}
            type="number"
            min="0"
            max="100"
            value={form.discount}
            onChange={(event) => set('discount', event.target.value)}
          />
        </div>
        {annualMonthly !== null && annualMonthly > 0 && (
          <p className="text-xs text-muted-foreground">{t.annualHint(String(Math.round(annualMonthly)))}</p>
        )}

        <div className="grid grid-cols-2 gap-3">
          <Input
            label={t.monitorsLabel}
            type="number"
            min="1"
            value={form.maxMonitors}
            onChange={(event) => set('maxMonitors', event.target.value)}
          />
          <Input
            label={t.browserMonitorsLabel}
            type="number"
            min="0"
            value={form.maxBrowser}
            onChange={(event) => set('maxBrowser', event.target.value)}
          />
        </div>

        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="mb-1 block text-sm font-normal text-placeholder">{t.minIntervalLabel}</label>
            <select
              className={selectClasses}
              value={form.minInterval}
              onChange={(event) => set('minInterval', Number(event.target.value))}
            >
              {t.intervalOptions.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="mb-1 block text-sm font-normal text-placeholder">{t.browserMinIntervalLabel}</label>
            <select
              className={selectClasses}
              value={form.browserMinInterval}
              onChange={(event) => set('browserMinInterval', Number(event.target.value))}
            >
              {t.intervalOptions
                .filter((option) => option.value >= 60)
                .map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
            </select>
          </div>
        </div>

        <div className="grid grid-cols-2 gap-3">
          <div>
            <Input
              label={t.teamMembersLabel}
              type="number"
              min="1"
              value={form.members}
              disabled={form.unlimitedMembers}
              placeholder={form.unlimitedMembers ? t.unlimited : ''}
              onChange={(event) => set('members', event.target.value)}
            />
            <label className="mt-1.5 flex items-center gap-2 text-xs text-muted-foreground">
              <input
                type="checkbox"
                checked={form.unlimitedMembers}
                onChange={(event) => set('unlimitedMembers', event.target.checked)}
              />
              {t.unlimited}
            </label>
          </div>
          <div>
            <label className="mb-1 block text-sm font-normal text-placeholder">{t.retentionLabel}</label>
            <select
              className={selectClasses}
              value={form.retention}
              onChange={(event) => set('retention', Number(event.target.value))}
            >
              {t.retentionOptions.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </div>
        </div>

        {message && (
          <p className="flex items-center gap-1.5 text-xs font-semibold text-primary">
            <CheckCircle2 className="h-3.5 w-3.5" />
            {message}
          </p>
        )}
        {error && <p className="text-xs font-semibold text-destructive">{error}</p>}

        <Button onClick={handleSave} isLoading={isSaving} className="w-full">
          <Save className="h-4 w-4" />
          {t.save(plan.name)}
        </Button>
      </CardContent>
    </Card>
  );
}

function PlansTab() {
  const t = useTexts({
    ru: {
      loadError: 'Не удалось загрузить тарифы',
      loading: 'Загрузка тарифов...',
      note: 'Изменения сразу применяются на странице тарифов. Действующие подписки сохраняют цену до продления; лимиты начнут применяться после запуска ограничений по тарифам.',
    },
    en: {
      loadError: 'Unable to load plans',
      loading: 'Loading plans...',
      note: 'Changes apply to the pricing page immediately. Existing subscriptions keep their price until renewal; limits are enforced once plan gating ships.',
    },
  });
  const [plans, setPlans] = useState<Plan[]>([]);
  const [error, setError] = useState('');

  useEffect(() => {
    let ignore = false;
    listPlans()
      .then((list) => {
        if (!ignore) {
          setPlans(list);
          setError('');
        }
      })
      .catch((err) => {
        if (!ignore) {
          setError(err instanceof ApiError ? err.message : t.loadError);
        }
      });
    return () => {
      ignore = true;
    };
  }, []);

  if (error) {
    return <div className="rounded-lg bg-destructive/10 p-4 text-sm text-destructive">{error}</div>;
  }
  if (plans.length === 0) {
    return <div className="rounded-lg bg-secondary p-4 text-sm text-muted-foreground">{t.loading}</div>;
  }

  return (
    <div className="space-y-6">
      <p className="text-sm text-muted-foreground">{t.note}</p>
      <div className="grid gap-4 lg:grid-cols-3">
        {plans.map((plan) => (
          <PlanCard
            key={plan.slug}
            plan={plan}
            onSaved={(updated) =>
              setPlans((current) => current.map((item) => (item.slug === updated.slug ? updated : item)))
            }
          />
        ))}
      </div>
    </div>
  );
}

function OrganizationsTab() {
  const t = useTexts({
    ru: {
      loadError: 'Не удалось загрузить организации',
      changePlanError: 'Не удалось сменить тариф',
      loading: 'Загрузка организаций...',
      title: (n: number) => `Организации (${n})`,
      members: (n: number) => `${n} ${plural(n, ['участник', 'участника', 'участников'])}`,
      monitors: (n: number) => `${n} ${plural(n, ['монитор', 'монитора', 'мониторов'])}`,
      since: (date: string) => `с ${date}`,
      planAria: (name: string) => `Тариф организации ${name}`,
    },
    en: {
      loadError: 'Unable to load organizations',
      changePlanError: 'Unable to change plan',
      loading: 'Loading organizations...',
      title: (n: number) => `Organizations (${n})`,
      members: (n: number) => `${n} members`,
      monitors: (n: number) => `${n} monitors`,
      since: (date: string) => `since ${date}`,
      planAria: (name: string) => `Plan of ${name}`,
    },
  });
  const [orgs, setOrgs] = useState<AdminOrg[]>([]);
  const [plans, setPlans] = useState<Plan[]>([]);
  const [error, setError] = useState('');
  const [rowError, setRowError] = useState<Record<number, string>>({});

  useEffect(() => {
    let ignore = false;
    Promise.all([listAdminOrgs(), listPlans()])
      .then(([orgList, planList]) => {
        if (!ignore) {
          setOrgs(orgList);
          setPlans(planList);
          setError('');
        }
      })
      .catch((err) => {
        if (!ignore) {
          setError(err instanceof ApiError ? err.message : t.loadError);
        }
      });
    return () => {
      ignore = true;
    };
  }, []);

  const handlePlanChange = async (org: AdminOrg, planSlug: string) => {
    setRowError((current) => ({ ...current, [org.id]: '' }));
    try {
      const updated = await setOrgPlan(org.id, planSlug);
      setOrgs((current) => current.map((item) => (item.id === updated.id ? updated : item)));
    } catch (err) {
      setRowError((current) => ({
        ...current,
        [org.id]: err instanceof ApiError ? err.message : t.changePlanError,
      }));
    }
  };

  if (error) {
    return <div className="rounded-lg bg-destructive/10 p-4 text-sm text-destructive">{error}</div>;
  }
  if (orgs.length === 0) {
    return <div className="rounded-lg bg-secondary p-4 text-sm text-muted-foreground">{t.loading}</div>;
  }

  return (
    <Card className="overflow-hidden">
      <CardHeader className="border-b border-border">
        <CardTitle className="flex items-center gap-2">
          <Building2 className="h-5 w-5 text-primary" />
          {t.title(orgs.length)}
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3 p-6">
        {orgs.map((org) => (
          <div
            key={org.id}
            className="flex flex-col gap-3 rounded-lg border border-border p-4 sm:flex-row sm:items-center sm:justify-between"
          >
            <div className="min-w-0">
              <div className="flex flex-wrap items-center gap-2">
                <p className="truncate text-sm font-semibold text-foreground">{org.name}</p>
                <span className="rounded-lg bg-secondary px-2 py-0.5 text-[11px] font-semibold text-muted-foreground">
                  {org.slug}
                </span>
              </div>
              <p className="mt-1 flex flex-wrap items-center gap-x-3 text-xs text-placeholder">
                <span className="inline-flex items-center gap-1">
                  <Users className="h-3.5 w-3.5" />
                  {t.members(org.members_count)}
                </span>
                <span className="inline-flex items-center gap-1">
                  <Activity className="h-3.5 w-3.5" />
                  {t.monitors(org.monitors_count)}
                </span>
                <span>{t.since(new Date(org.created_at).toLocaleDateString())}</span>
              </p>
              {rowError[org.id] && (
                <p className="mt-1 text-xs font-semibold text-destructive">{rowError[org.id]}</p>
              )}
            </div>
            <select
              aria-label={t.planAria(org.name)}
              className={cn(selectClasses, 'w-auto shrink-0')}
              value={org.plan_slug}
              onChange={(event) => handlePlanChange(org, event.target.value)}
            >
              {plans.map((plan) => (
                <option key={plan.slug} value={plan.slug}>
                  {plan.name}
                </option>
              ))}
            </select>
          </div>
        ))}
      </CardContent>
    </Card>
  );
}

export default function Admin() {
  const t = useTexts({
    ru: {
      tabs: [
        { id: 'overview', label: 'Обзор' },
        { id: 'plans', label: 'Тарифы' },
        { id: 'organizations', label: 'Организации' },
      ] as { id: TabId; label: string }[],
      checkingAccess: 'Проверка доступа...',
      adminsOnly: 'Эта страница доступна только администраторам платформы.',
      badge: 'Админ платформы',
      title: 'Администрирование сервиса',
      description:
        'Состояние всей платформы, тарифы и организации. Изменения здесь затрагивают все рабочие пространства.',
    },
    en: {
      tabs: [
        { id: 'overview', label: 'Overview' },
        { id: 'plans', label: 'Plans' },
        { id: 'organizations', label: 'Organizations' },
      ] as { id: TabId; label: string }[],
      checkingAccess: 'Checking access...',
      adminsOnly: 'This page is available to platform administrators only.',
      badge: 'Platform admin',
      title: 'Service administration',
      description: 'Platform-wide health, pricing plans, and organizations. Changes here affect every workspace.',
    },
  });
  const [tab, setTab] = useState<TabId>('overview');
  const [access, setAccess] = useState<'loading' | 'denied' | 'granted'>('loading');

  useEffect(() => {
    let ignore = false;
    getMe()
      .then((me) => {
        if (!ignore) {
          setAccess(me.is_superuser ? 'granted' : 'denied');
        }
      })
      .catch(() => {
        if (!ignore) {
          setAccess('denied');
        }
      });
    return () => {
      ignore = true;
    };
  }, []);

  if (access === 'loading') {
    return <div className="rounded-lg bg-secondary p-4 text-sm text-muted-foreground">{t.checkingAccess}</div>;
  }
  if (access === 'denied') {
    return (
      <div className="rounded-lg bg-card p-6 text-sm text-muted-foreground shadow-card">
        {t.adminsOnly}
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <section className="rounded-lg bg-card p-6 shadow-card">
        <p className="flex items-center gap-2 text-sm font-semibold text-primary">
          <ShieldCheck className="h-4 w-4" />
          {t.badge}
        </p>
        <h1 className="mt-2 text-2xl font-semibold leading-8 text-foreground">{t.title}</h1>
        <p className="mt-3 max-w-3xl text-sm leading-5 text-muted-foreground">{t.description}</p>
      </section>

      <div className="flex gap-2">
        {t.tabs.map((item) => (
          <button
            key={item.id}
            type="button"
            onClick={() => setTab(item.id)}
            className={cn(
              'rounded-lg px-4 py-2 text-sm font-medium transition-colors',
              tab === item.id ? 'bg-accent text-primary' : 'bg-card text-muted-foreground shadow-card hover:text-primary'
            )}
          >
            {item.label}
          </button>
        ))}
      </div>

      {tab === 'overview' && <OverviewTab />}
      {tab === 'plans' && <PlansTab />}
      {tab === 'organizations' && <OrganizationsTab />}
    </div>
  );
}
