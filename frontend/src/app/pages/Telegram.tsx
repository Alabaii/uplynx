import { useEffect, useState } from 'react';
import { Bell, BellRing, Bot, CheckCircle2, Mail, Send, Smartphone, TriangleAlert } from 'lucide-react';
import { Button } from '../components/ui/Button';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/Card';
import { Input } from '../components/ui/Input';
import { ApiError, connectTelegram, getMe, getTelegram, listOrgs, testTelegram, updateCurrentOrg } from '../api';
import { useMeta } from '../meta-context';
import { usePushNotifications, type PushStatus } from '../pwa/usePushNotifications';
import { cn } from '../utils/cn';

const alertScopes = [
  { id: 'down', label: 'Down', description: 'Critical failures and timeouts' },
  { id: 'degraded', label: 'Degraded', description: 'Slow but not fully broken checks' },
  { id: 'recovered', label: 'Recovered', description: 'Follow-up signal when status returns to green' },
] as const;

type AlertScope = (typeof alertScopes)[number]['id'];

export default function TelegramSettings() {
  const [connected, setConnected] = useState(false);
  const [maskedToken, setMaskedToken] = useState('');
  const [token, setToken] = useState('');
  const [chatId, setChatId] = useState('');
  const [selectedAlerts, setSelectedAlerts] = useState<AlertScope[]>(['down', 'recovered']);
  const [isSaving, setIsSaving] = useState(false);
  const [isTesting, setIsTesting] = useState(false);
  const [message, setMessage] = useState<{ tone: 'success' | 'error'; text: string } | null>(null);

  useEffect(() => {
    let ignore = false;

    getTelegram()
      .then((integration) => {
        if (!ignore && integration.connected) {
          setConnected(true);
          setChatId(integration.chat_id ?? '');
          setSelectedAlerts(integration.alert_scopes.filter((scope): scope is AlertScope =>
            alertScopes.some((item) => item.id === scope)
          ));
          setMaskedToken(integration.bot_token_masked ?? '');
        }
      })
      .catch(() => {
        // No integration yet (or endpoint unavailable) - keep the empty form.
      });

    return () => {
      ignore = true;
    };
  }, []);

  const toggleScope = (scope: AlertScope) => {
    setSelectedAlerts((current) =>
      current.includes(scope) ? current.filter((item) => item !== scope) : [...current, scope]
    );
  };

  const handleSave = async (event: React.FormEvent) => {
    event.preventDefault();
    setIsSaving(true);
    setMessage(null);

    try {
      const integration = await connectTelegram({ bot_token: token, chat_id: chatId, alert_scopes: selectedAlerts });
      setConnected(true);
      setChatId(integration.chat_id ?? chatId);
      setToken('');
      setMaskedToken(integration.bot_token_masked ?? '');
      setMessage({ tone: 'success', text: 'Telegram settings saved.' });
    } catch (error) {
      setMessage({
        tone: 'error',
        text: error instanceof ApiError ? error.message : 'Unable to save Telegram settings.',
      });
    } finally {
      setIsSaving(false);
    }
  };

  const handleTest = async () => {
    setIsTesting(true);
    setMessage(null);

    try {
      const result = await testTelegram();
      setMessage(
        result.ok
          ? { tone: 'success', text: 'Test alert sent. Check your Telegram chat.' }
          : { tone: 'error', text: result.detail }
      );
    } catch (error) {
      setMessage({
        tone: 'error',
        text: error instanceof ApiError ? error.message : 'Unable to send a test message.',
      });
    } finally {
      setIsTesting(false);
    }
  };

  return (
    <div className="space-y-6">
      <section className="rounded-lg bg-card p-6 shadow-card">
        <div className="flex flex-col gap-6 xl:flex-row xl:items-end xl:justify-between">
          <div>
            <p className="text-sm font-semibold text-primary">Telegram integration</p>
            <h1 className="mt-2 text-2xl font-semibold leading-8 text-foreground">Route incidents to operators</h1>
            <p className="mt-3 max-w-3xl text-sm leading-5 text-muted-foreground">
              Connect a Telegram bot to receive alerts when monitors go down, degrade, or recover.
            </p>
          </div>

          {connected ? (
            <div className="rounded-lg bg-accent px-4 py-3 text-sm text-accent-foreground">
              Connected to chat {chatId || 'unknown'}
            </div>
          ) : (
            <div className="rounded-lg bg-secondary px-4 py-3 text-sm text-muted-foreground">
              Not connected yet
            </div>
          )}
        </div>
      </section>

      <div className="grid gap-6 xl:grid-cols-[1fr_0.9fr]">
        <Card className="overflow-hidden">
          <CardHeader className="border-b border-border">
            <CardTitle className="flex items-center gap-2">
              <Send className="h-5 w-5 text-primary" />
              Configure bot
            </CardTitle>
          </CardHeader>

          <CardContent className="p-6">
            <form onSubmit={handleSave} className="space-y-6">
              <div className="grid gap-4">
                <Input
                  label="Bot token"
                  type="password"
                  value={token}
                  onChange={(event) => setToken(event.target.value)}
                  placeholder={maskedToken || '123456789:AA...'}
                  required
                />
                <Input
                  label="Chat ID"
                  value={chatId}
                  onChange={(event) => setChatId(event.target.value)}
                  placeholder="-1001234567890"
                  required
                />
              </div>

              <div className="space-y-3">
                <p className="text-sm font-semibold text-foreground">Alert scope</p>
                <div className="grid gap-3 md:grid-cols-3">
                  {alertScopes.map((scope) => {
                    const active = selectedAlerts.includes(scope.id);

                    return (
                      <button
                        key={scope.id}
                        type="button"
                        onClick={() => toggleScope(scope.id)}
                        className={cn(
                          'rounded-lg border p-4 text-left transition-colors',
                          active ? 'border-transparent bg-accent' : 'border-border bg-card hover:border-input-border-hover'
                        )}
                      >
                        <div className="flex items-center justify-between gap-3">
                          <p className="font-semibold text-foreground">{scope.label}</p>
                          {active && <CheckCircle2 className="h-4 w-4 text-primary" />}
                        </div>
                        <p className="mt-2 text-sm leading-5 text-muted-foreground">{scope.description}</p>
                      </button>
                    );
                  })}
                </div>
              </div>

              {message && (
                <div
                  className={cn(
                    'rounded-lg p-4 text-sm',
                    message.tone === 'success'
                      ? 'bg-accent text-accent-foreground'
                      : 'bg-destructive/10 text-destructive'
                  )}
                >
                  {message.text}
                </div>
              )}

              <div className="flex flex-col gap-3 border-t border-border pt-5 sm:flex-row sm:justify-end">
                <Button
                  type="button"
                  variant="ghost"
                  onClick={handleTest}
                  isLoading={isTesting}
                  disabled={!connected}
                >
                  Test connection
                </Button>
                <Button type="submit" isLoading={isSaving}>
                  <Send className="h-4 w-4" />
                  Save settings
                </Button>
              </div>
            </form>
          </CardContent>
        </Card>

        <div className="space-y-6">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Bot className="h-5 w-5 text-primary" />
                Delivery preview
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-4 text-sm text-muted-foreground">
              <div className="rounded-lg bg-secondary p-4">
                <p className="font-semibold text-foreground">Sample message</p>
                <p className="mt-3 text-sm leading-5">
                  `DOWN` Monitor `api-health` failed: HTTP 500 after 3 retries.
                </p>
              </div>
              <div className="rounded-lg bg-secondary p-4">
                <p className="font-semibold text-foreground">Current scopes</p>
                <p className="mt-3">{selectedAlerts.join(', ') || 'No alerts selected'}</p>
              </div>
            </CardContent>
          </Card>

          <BrowserPushCard />

          <EmailAlertsCard />

          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <BellRing className="h-5 w-5 text-primary" />
                Platform notes
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-3 text-sm leading-5 text-muted-foreground">
              <InfoRow icon={Smartphone} text="Browser push and Telegram are independent channels - enable either or both." />
              <InfoRow icon={TriangleAlert} text="iOS web push requires iOS 16.4+ and an installed Home Screen app, even when Telegram is configured." />
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}

const pushStatusText: Record<PushStatus, string> = {
  loading: 'Checking browser support...',
  unsupported: 'Push requires the installed PWA (production build). Open the app from your home screen to enable it.',
  'disabled-on-server': 'Push is not configured on this server. Ask an administrator to set VAPID keys.',
  'permission-denied': 'Notifications are blocked for this site. Allow them in the browser settings and reload.',
  subscribed: 'This device receives push alerts when monitors change status.',
  'not-subscribed': 'This device is not subscribed yet. Enable push to get alerts even when the app is closed.',
};

function BrowserPushCard() {
  const { status, isBusy, error, enable, disable } = usePushNotifications();
  const canToggle = status === 'subscribed' || status === 'not-subscribed';

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Bell className="h-5 w-5 text-primary" />
          Browser push
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4 text-sm leading-5 text-muted-foreground">
        <div className="flex items-center justify-between gap-3 rounded-lg bg-secondary p-4">
          <div>
            <p className="font-semibold text-foreground">Status</p>
            <p className="mt-1">{status === 'subscribed' ? 'Enabled on this device' : 'Not active'}</p>
          </div>
          <span
            className={cn(
              'rounded-lg px-3 py-1 text-xs font-semibold',
              status === 'subscribed' ? 'bg-accent text-accent-foreground' : 'bg-card text-muted-foreground'
            )}
          >
            {status === 'subscribed' ? 'On' : 'Off'}
          </span>
        </div>

        <p>{pushStatusText[status]}</p>

        {error && <p className="rounded-lg bg-destructive/10 p-3 text-destructive">{error}</p>}

        {canToggle && (
          <Button
            type="button"
            variant={status === 'subscribed' ? 'ghost' : 'primary'}
            onClick={status === 'subscribed' ? disable : enable}
            isLoading={isBusy}
          >
            <Bell className="h-4 w-4" />
            {status === 'subscribed' ? 'Disable push' : 'Enable push'}
          </Button>
        )}
      </CardContent>
    </Card>
  );
}

function EmailAlertsCard() {
  const meta = useMeta();
  const emailEnabled = meta?.email_enabled ?? false;
  const [isOwner, setIsOwner] = useState(false);
  const [emails, setEmails] = useState<string[]>([]);
  const [draft, setDraft] = useState('');
  const [isSaving, setIsSaving] = useState(false);
  const [message, setMessage] = useState<{ tone: 'success' | 'error'; text: string } | null>(null);

  useEffect(() => {
    let ignore = false;

    Promise.all([getMe(), listOrgs()])
      .then(([me, orgs]) => {
        if (ignore) return;
        setIsOwner(me.organization?.role === 'owner');
        const current = orgs.find((org) => org.id === me.organization?.id);
        const list = current?.alert_emails ?? [];
        setEmails(list);
        setDraft(list.join(', '));
      })
      .catch(() => {
        // данные организации недоступны — карточка остаётся в read-only-состоянии
      });

    return () => {
      ignore = true;
    };
  }, []);

  const handleSave = async (event: React.FormEvent) => {
    event.preventDefault();
    setIsSaving(true);
    setMessage(null);

    const parsed = draft
      .split(',')
      .map((item) => item.trim())
      .filter(Boolean);

    try {
      const updated = await updateCurrentOrg({ alert_emails: parsed });
      const list = updated.alert_emails ?? parsed;
      setEmails(list);
      setDraft(list.join(', '));
      setMessage({ tone: 'success', text: 'Email recipients saved.' });
    } catch (error) {
      setMessage({
        tone: 'error',
        text: error instanceof ApiError ? error.message : 'Unable to save email recipients.',
      });
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Mail className="h-5 w-5 text-primary" />
          Email alerts
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4 text-sm leading-5 text-muted-foreground">
        {!emailEnabled && (
          <p className="rounded-lg bg-secondary p-4">
            Email is not configured on this server (SMTP_HOST). Recipients are stored, but no emails are sent.
          </p>
        )}

        {isOwner ? (
          <form onSubmit={handleSave} className="space-y-4">
            <div>
              <label htmlFor="alert-emails" className="mb-1 block text-sm font-normal text-placeholder">
                Recipients (comma-separated, up to 10)
              </label>
              <textarea
                id="alert-emails"
                value={draft}
                onChange={(event) => setDraft(event.target.value)}
                rows={3}
                placeholder="ops@company.com, oncall@company.com"
                className="w-full rounded-lg border border-input bg-input-background px-3 py-2 text-base text-foreground placeholder:text-placeholder transition-colors hover:border-input-border-hover focus:border-input-border-hover focus:outline-none focus:ring-2 focus:ring-ring/20"
              />
            </div>

            {message && (
              <div
                className={cn(
                  'rounded-lg p-4 text-sm',
                  message.tone === 'success'
                    ? 'bg-accent text-accent-foreground'
                    : 'bg-destructive/10 text-destructive'
                )}
              >
                {message.text}
              </div>
            )}

            <div className="flex justify-end">
              <Button type="submit" isLoading={isSaving}>
                <Mail className="h-4 w-4" />
                Save recipients
              </Button>
            </div>
          </form>
        ) : (
          <div className="rounded-lg bg-secondary p-4">
            <p className="font-semibold text-foreground">Recipients</p>
            <p className="mt-2">
              {emails.length
                ? emails.join(', ')
                : 'No recipients configured. Ask the workspace owner to add some.'}
            </p>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function InfoRow({ icon: Icon, text }: { icon: typeof Bot; text: string }) {
  return (
    <div className="rounded-lg border border-border p-4">
      <div className="flex items-start gap-3">
        <div className="mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-accent text-primary">
          <Icon className="h-4 w-4" />
        </div>
        <p>{text}</p>
      </div>
    </div>
  );
}
