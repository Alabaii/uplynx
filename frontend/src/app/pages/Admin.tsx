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

type TabId = 'overview' | 'plans' | 'organizations';

const tabs: { id: TabId; label: string }[] = [
  { id: 'overview', label: 'Overview' },
  { id: 'plans', label: 'Plans' },
  { id: 'organizations', label: 'Organizations' },
];

const intervalOptions = [
  { value: 10, label: '10 seconds' },
  { value: 30, label: '30 seconds' },
  { value: 60, label: '1 minute' },
  { value: 300, label: '5 minutes' },
  { value: 900, label: '15 minutes' },
];

const retentionOptions = [
  { value: 30, label: '30 days' },
  { value: 90, label: '90 days' },
  { value: 365, label: '1 year' },
];

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
      .catch((err) => setError(err instanceof ApiError ? err.message : 'Unable to load platform stats'))
      .finally(() => setIsLoading(false));
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  if (error) {
    return <div className="rounded-lg bg-destructive/10 p-4 text-sm text-destructive">{error}</div>;
  }
  if (!data) {
    return <div className="rounded-lg bg-secondary p-4 text-sm text-muted-foreground">Loading platform stats...</div>;
  }

  const scheduler = data.scheduler;
  const schedulerValue = scheduler.beat_age_seconds === null ? 'no heartbeat' : `${scheduler.beat_age_seconds}s ago`;

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <p className="text-sm text-muted-foreground">Live platform totals across every organization.</p>
        <Button variant="outline" size="sm" onClick={load} isLoading={isLoading}>
          <RefreshCw className="h-4 w-4" />
          Refresh
        </Button>
      </div>

      <div className="grid grid-cols-2 gap-4 md:grid-cols-3 xl:grid-cols-4">
        <StatCard label="Users" value={String(data.users_total)} />
        <StatCard label="Organizations" value={String(data.orgs_total)} />
        <StatCard
          label="Monitors"
          value={String(data.monitors_total)}
          hint={`${data.monitors_enabled} enabled · ${data.monitors_browser} browser`}
        />
        <StatCard label="Checks (24h)" value={data.checks_24h.toLocaleString()} />
        <StatCard label="Open incidents" value={String(data.incidents_open)} alert={data.incidents_open > 0} />
        <StatCard
          label="Scheduler heartbeat"
          value={schedulerValue}
          hint={scheduler.overdue_monitors > 0 ? `${scheduler.overdue_monitors} monitors overdue` : 'on schedule'}
          alert={scheduler.stale}
        />
      </div>

      <Card>
        <CardHeader className="border-b border-border">
          <CardTitle className="flex items-center gap-2">
            <Gauge className="h-5 w-5 text-primary" />
            Queues
          </CardTitle>
        </CardHeader>
        <CardContent className="p-6">
          {data.queues === null ? (
            <div className="flex items-center gap-2 rounded-lg bg-destructive/10 p-4 text-sm text-destructive">
              <AlertTriangle className="h-4 w-4" />
              RabbitMQ is unreachable — queue depths unavailable.
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
                      <p className="text-xs text-placeholder">{isDead ? 'dead-letter queue' : 'work queue'}</p>
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
    price: (plan.price_monthly_cents / 100).toString(),
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
        price_monthly_cents: Math.round(Number.parseFloat(form.price || '0') * 100),
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
      setMessage('Saved.');
    } catch (err) {
      setError(err instanceof ApiError ? err.message : 'Unable to save plan');
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
            label="Price, $/month"
            type="number"
            min="0"
            step="0.5"
            value={form.price}
            onChange={(event) => set('price', event.target.value)}
          />
          <Input
            label="Annual discount, %"
            type="number"
            min="0"
            max="100"
            value={form.discount}
            onChange={(event) => set('discount', event.target.value)}
          />
        </div>
        {annualMonthly !== null && annualMonthly > 0 && (
          <p className="text-xs text-muted-foreground">≈ ${annualMonthly.toFixed(2)}/month billed annually</p>
        )}

        <div className="grid grid-cols-2 gap-3">
          <Input
            label="Monitors"
            type="number"
            min="1"
            value={form.maxMonitors}
            onChange={(event) => set('maxMonitors', event.target.value)}
          />
          <Input
            label="Browser monitors"
            type="number"
            min="0"
            value={form.maxBrowser}
            onChange={(event) => set('maxBrowser', event.target.value)}
          />
        </div>

        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="mb-1 block text-sm font-normal text-placeholder">Min interval</label>
            <select
              className={selectClasses}
              value={form.minInterval}
              onChange={(event) => set('minInterval', Number(event.target.value))}
            >
              {intervalOptions.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="mb-1 block text-sm font-normal text-placeholder">Browser min interval</label>
            <select
              className={selectClasses}
              value={form.browserMinInterval}
              onChange={(event) => set('browserMinInterval', Number(event.target.value))}
            >
              {intervalOptions
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
              label="Team members"
              type="number"
              min="1"
              value={form.members}
              disabled={form.unlimitedMembers}
              placeholder={form.unlimitedMembers ? 'Unlimited' : ''}
              onChange={(event) => set('members', event.target.value)}
            />
            <label className="mt-1.5 flex items-center gap-2 text-xs text-muted-foreground">
              <input
                type="checkbox"
                checked={form.unlimitedMembers}
                onChange={(event) => set('unlimitedMembers', event.target.checked)}
              />
              Unlimited
            </label>
          </div>
          <div>
            <label className="mb-1 block text-sm font-normal text-placeholder">History retention</label>
            <select
              className={selectClasses}
              value={form.retention}
              onChange={(event) => set('retention', Number(event.target.value))}
            >
              {retentionOptions.map((option) => (
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
          Save {plan.name}
        </Button>
      </CardContent>
    </Card>
  );
}

function PlansTab() {
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
          setError(err instanceof ApiError ? err.message : 'Unable to load plans');
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
    return <div className="rounded-lg bg-secondary p-4 text-sm text-muted-foreground">Loading plans...</div>;
  }

  return (
    <div className="space-y-6">
      <p className="text-sm text-muted-foreground">
        Changes apply to the pricing page immediately. Existing subscriptions keep their price until renewal;
        limits are enforced once plan gating ships.
      </p>
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
          setError(err instanceof ApiError ? err.message : 'Unable to load organizations');
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
        [org.id]: err instanceof ApiError ? err.message : 'Unable to change plan',
      }));
    }
  };

  if (error) {
    return <div className="rounded-lg bg-destructive/10 p-4 text-sm text-destructive">{error}</div>;
  }
  if (orgs.length === 0) {
    return <div className="rounded-lg bg-secondary p-4 text-sm text-muted-foreground">Loading organizations...</div>;
  }

  return (
    <Card className="overflow-hidden">
      <CardHeader className="border-b border-border">
        <CardTitle className="flex items-center gap-2">
          <Building2 className="h-5 w-5 text-primary" />
          Organizations ({orgs.length})
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
                  {org.members_count} members
                </span>
                <span className="inline-flex items-center gap-1">
                  <Activity className="h-3.5 w-3.5" />
                  {org.monitors_count} monitors
                </span>
                <span>since {new Date(org.created_at).toLocaleDateString()}</span>
              </p>
              {rowError[org.id] && (
                <p className="mt-1 text-xs font-semibold text-destructive">{rowError[org.id]}</p>
              )}
            </div>
            <select
              aria-label={`Plan of ${org.name}`}
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
    return <div className="rounded-lg bg-secondary p-4 text-sm text-muted-foreground">Checking access...</div>;
  }
  if (access === 'denied') {
    return (
      <div className="rounded-lg bg-card p-6 text-sm text-muted-foreground shadow-card">
        This page is available to platform administrators only.
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <section className="rounded-lg bg-card p-6 shadow-card">
        <p className="flex items-center gap-2 text-sm font-semibold text-primary">
          <ShieldCheck className="h-4 w-4" />
          Platform admin
        </p>
        <h1 className="mt-2 text-2xl font-semibold leading-8 text-foreground">Service administration</h1>
        <p className="mt-3 max-w-3xl text-sm leading-5 text-muted-foreground">
          Platform-wide health, pricing plans, and organizations. Changes here affect every workspace.
        </p>
      </section>

      <div className="flex gap-2">
        {tabs.map((item) => (
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
