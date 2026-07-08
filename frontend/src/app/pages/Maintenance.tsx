import { useCallback, useEffect, useState } from 'react';
import { CalendarPlus, Trash2, Wrench } from 'lucide-react';
import { Button } from '../components/ui/Button';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/Card';
import { Input } from '../components/ui/Input';
import {
  ApiError,
  createMaintenance,
  deleteMaintenance,
  getMe,
  listMaintenance,
  listMonitors,
  type MaintenanceWindow,
  type Monitor,
  type OrgRole,
} from '../api';
import { cn } from '../utils/cn';

type WindowState = 'active' | 'scheduled' | 'finished';

const stateBadgeClasses: Record<WindowState, string> = {
  active: 'bg-accent text-primary',
  scheduled: 'bg-secondary text-muted-foreground',
  finished: 'bg-muted text-muted-foreground',
};

const stateLabels: Record<WindowState, string> = {
  active: 'Active',
  scheduled: 'Scheduled',
  finished: 'Finished',
};

function windowState(window: MaintenanceWindow): WindowState {
  if (window.active) {
    return 'active';
  }

  return new Date(window.starts_at).getTime() > Date.now() ? 'scheduled' : 'finished';
}

function formatPeriod(window: MaintenanceWindow): string {
  return `${new Date(window.starts_at).toLocaleString()} — ${new Date(window.ends_at).toLocaleString()}`;
}

export default function Maintenance() {
  const [windows, setWindows] = useState<MaintenanceWindow[]>([]);
  const [monitors, setMonitors] = useState<Monitor[]>([]);
  const [myRole, setMyRole] = useState<OrgRole>('viewer');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const [formMonitor, setFormMonitor] = useState('');
  const [formStart, setFormStart] = useState('');
  const [formEnd, setFormEnd] = useState('');
  const [formNote, setFormNote] = useState('');
  const [formError, setFormError] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);

  const canManage = myRole === 'admin' || myRole === 'owner';

  const load = useCallback(() => {
    listMaintenance()
      .then((rows) => {
        setWindows(rows);
        setError('');
      })
      .catch((error) => {
        setError(error instanceof Error ? error.message : 'Unable to load maintenance windows');
      })
      .finally(() => {
        setLoading(false);
      });
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    let ignore = false;

    Promise.all([getMe(), listMonitors()])
      .then(([me, monitorList]) => {
        if (!ignore) {
          setMyRole(me.organization?.role ?? 'viewer');
          setMonitors(monitorList);
        }
      })
      .catch(() => {
        // форма создания просто останется скрытой без роли
      });

    return () => {
      ignore = true;
    };
  }, []);

  const activeCount = windows.filter((window) => window.active).length;

  const handleCreate = async (event: React.FormEvent) => {
    event.preventDefault();
    setFormError('');
    setIsSubmitting(true);

    try {
      await createMaintenance({
        monitor_id: formMonitor || null,
        starts_at: new Date(formStart).toISOString(),
        ends_at: new Date(formEnd).toISOString(),
        note: formNote.trim() || undefined,
      });
      setFormMonitor('');
      setFormStart('');
      setFormEnd('');
      setFormNote('');
      load();
    } catch (error) {
      setFormError(error instanceof ApiError ? error.message : 'Unable to create maintenance window');
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleCancel = async (window: MaintenanceWindow) => {
    const target = window.monitor_name ?? 'all monitors';

    if (!globalThis.confirm(`Cancel the maintenance window for ${target}?`)) {
      return;
    }

    setError('');

    try {
      await deleteMaintenance(window.id);
      setWindows((current) => current.filter((item) => item.id !== window.id));
    } catch (error) {
      setError(error instanceof ApiError ? error.message : 'Unable to cancel the maintenance window');
    }
  };

  return (
    <div className="space-y-6">
      <section className="overflow-hidden rounded-lg bg-card p-6 shadow-card">
        <div className="flex flex-col gap-6 xl:flex-row xl:items-end xl:justify-between">
          <div className="max-w-3xl">
            <p className="text-sm font-semibold text-primary">Planned work</p>
            <h1 className="mt-2 text-2xl font-semibold leading-8 text-foreground">Maintenance windows</h1>
            <p className="mt-3 text-sm leading-6 text-muted-foreground">
              While a window is active, checks for the affected monitors are paused entirely: no alerts, no
              incidents, no uptime penalty. Checks resume right after the window ends.
            </p>
          </div>

          <div className="flex items-center gap-3 rounded-lg bg-secondary px-4 py-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-accent text-primary">
              <Wrench className="h-5 w-5" />
            </div>
            <div>
              <p className="text-xs text-placeholder">Active now</p>
              <p className="text-2xl font-semibold leading-7 text-foreground">{activeCount}</p>
            </div>
          </div>
        </div>
      </section>

      {error && <div className="rounded-lg bg-destructive/10 p-4 text-sm text-destructive">{error}</div>}

      {canManage && (
        <Card>
          <CardHeader className="border-b border-border">
            <CardTitle className="flex items-center gap-2">
              <CalendarPlus className="h-5 w-5 text-primary" />
              Schedule maintenance
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-4 p-6">
            {formError && <div className="rounded-lg bg-destructive/10 p-4 text-sm text-destructive">{formError}</div>}

            <form onSubmit={handleCreate} className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
              <div>
                <label htmlFor="maintenance-monitor" className="mb-1 block text-sm font-normal text-placeholder">
                  Monitor
                </label>
                <select
                  id="maintenance-monitor"
                  value={formMonitor}
                  onChange={(event) => setFormMonitor(event.target.value)}
                  className="h-11 w-full rounded-lg border border-input bg-input-background px-3 text-base text-foreground transition-colors hover:border-input-border-hover focus:border-input-border-hover focus:outline-none focus:ring-2 focus:ring-ring/20"
                >
                  <option value="">All monitors</option>
                  {monitors.map((monitor) => (
                    <option key={monitor.id} value={monitor.id}>
                      {monitor.name}
                    </option>
                  ))}
                </select>
              </div>
              <Input
                label="Starts"
                type="datetime-local"
                value={formStart}
                onChange={(event) => setFormStart(event.target.value)}
                required
              />
              <Input
                label="Ends"
                type="datetime-local"
                value={formEnd}
                onChange={(event) => setFormEnd(event.target.value)}
                required
              />
              <Input
                label="Note (optional)"
                value={formNote}
                onChange={(event) => setFormNote(event.target.value)}
                placeholder="Database upgrade"
                maxLength={300}
              />
              <div className="md:col-span-2 xl:col-span-4">
                <Button type="submit" isLoading={isSubmitting}>
                  <CalendarPlus className="h-4 w-4" />
                  Schedule window
                </Button>
              </div>
            </form>
          </CardContent>
        </Card>
      )}

      <Card className="overflow-hidden">
        <CardHeader className="border-b border-border">
          <CardTitle className="flex items-center gap-2">
            <Wrench className="h-5 w-5 text-primary" />
            Maintenance windows
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-3 p-4 md:p-6">
          {loading ? (
            <div className="rounded-lg border border-dashed border-border bg-secondary p-12 text-center">
              <p className="text-lg font-semibold text-foreground">Loading maintenance windows...</p>
            </div>
          ) : windows.length === 0 ? (
            <div className="rounded-lg border border-dashed border-border bg-secondary p-12 text-center">
              <p className="text-lg font-semibold text-foreground">No maintenance windows</p>
              <p className="mt-2 text-sm text-placeholder">
                Schedule one before planned work to pause checks and keep alerts quiet.
              </p>
            </div>
          ) : (
            windows.map((window) => {
              const state = windowState(window);

              return (
                <div key={window.id} className="rounded-lg border border-border p-4">
                  <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
                    <div className="min-w-0 space-y-2">
                      <div className="flex flex-wrap items-center gap-3">
                        <span
                          className={cn(
                            'inline-flex items-center rounded-lg px-2.5 py-1 text-xs font-semibold',
                            stateBadgeClasses[state]
                          )}
                        >
                          {stateLabels[state]}
                        </span>
                        <p className="text-sm font-semibold text-foreground">
                          {window.monitor_name ?? 'All monitors'}
                        </p>
                      </div>
                      <p className="text-sm text-muted-foreground">{formatPeriod(window)}</p>
                      {window.note && <p className="text-xs text-placeholder">{window.note}</p>}
                      {window.created_by_email && (
                        <p className="text-xs text-placeholder">Scheduled by {window.created_by_email}</p>
                      )}
                    </div>

                    {canManage && state !== 'finished' && (
                      <Button
                        variant="ghost"
                        size="sm"
                        className="shrink-0 text-destructive"
                        onClick={() => handleCancel(window)}
                      >
                        <Trash2 className="h-4 w-4" />
                        Cancel
                      </Button>
                    )}
                  </div>
                </div>
              );
            })
          )}
        </CardContent>
      </Card>
    </div>
  );
}
