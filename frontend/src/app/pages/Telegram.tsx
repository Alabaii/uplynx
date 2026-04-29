import { useState } from 'react';
import { BellRing, Bot, CheckCircle2, Send, Smartphone, TriangleAlert } from 'lucide-react';
import { Button } from '../components/ui/Button';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/Card';
import { Input } from '../components/ui/Input';
import { getTelegramIntegration } from '../data/mockMonitoring';
import { cn } from '../utils/cn';

const alertScopes = [
  { id: 'down', label: 'Down', description: 'Critical failures and timeouts' },
  { id: 'degraded', label: 'Degraded', description: 'Slow but not fully broken checks' },
  { id: 'recovered', label: 'Recovered', description: 'Follow-up signal when status returns to green' },
] as const;

export default function TelegramSettings() {
  const integration = getTelegramIntegration();
  const [token, setToken] = useState('123456789:mock-demo-token');
  const [chatId, setChatId] = useState(integration.chatId);
  const [selectedAlerts, setSelectedAlerts] = useState(integration.alerts);
  const [isTesting, setIsTesting] = useState(false);
  const [status, setStatus] = useState<'idle' | 'success' | 'error'>('idle');

  const toggleScope = (scope: (typeof alertScopes)[number]['id']) => {
    setSelectedAlerts((current) =>
      current.includes(scope) ? current.filter((item) => item !== scope) : [...current, scope]
    );
  };

  const handleTest = (event: React.FormEvent) => {
    event.preventDefault();
    setIsTesting(true);
    setStatus('idle');

    window.setTimeout(() => {
      setStatus(token.length > 10 && chatId.length > 5 ? 'success' : 'error');
      setIsTesting(false);
    }, 900);
  };

  return (
    <div className="space-y-6">
      <section className="rounded-[1.75rem] border border-slate-200 bg-white p-6 shadow-sm">
        <div className="flex flex-col gap-6 xl:flex-row xl:items-end xl:justify-between">
          <div>
            <p className="text-sm font-semibold uppercase tracking-[0.22em] text-teal-700">Telegram integration</p>
            <h1 className="mt-2 text-3xl font-semibold tracking-tight text-slate-950">Route incidents to operators</h1>
            <p className="mt-3 max-w-3xl text-sm leading-6 text-slate-600">
              This prototype shows connection setup, alert scope control, and test message feedback. Real Bot API calls
              can drop into the same UI later.
            </p>
          </div>

          <div className="rounded-[1.5rem] border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-800">
            Connected as {integration.botName}
          </div>
        </div>
      </section>

      <div className="grid gap-6 xl:grid-cols-[1fr_0.9fr]">
        <Card className="overflow-hidden">
          <CardHeader className="border-b border-slate-200 bg-slate-50/80">
            <CardTitle className="flex items-center gap-2 text-xl">
              <Send className="h-5 w-5 text-teal-700" />
              Configure bot
            </CardTitle>
          </CardHeader>

          <CardContent className="p-6">
            <form onSubmit={handleTest} className="space-y-6">
              <div className="grid gap-4">
                <Input
                  label="Bot token"
                  type="password"
                  value={token}
                  onChange={(event) => setToken(event.target.value)}
                  placeholder="123456789:AA..."
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
                <p className="text-sm font-semibold text-slate-900">Alert scope</p>
                <div className="grid gap-3 md:grid-cols-3">
                  {alertScopes.map((scope) => {
                    const active = selectedAlerts.includes(scope.id);

                    return (
                      <button
                        key={scope.id}
                        type="button"
                        onClick={() => toggleScope(scope.id)}
                        className={cn(
                          'rounded-[1.25rem] border p-4 text-left transition-colors',
                          active ? 'border-teal-200 bg-teal-50' : 'border-slate-200 bg-white hover:border-slate-300'
                        )}
                      >
                        <div className="flex items-center justify-between gap-3">
                          <p className="font-semibold text-slate-900">{scope.label}</p>
                          {active && <CheckCircle2 className="h-4 w-4 text-teal-700" />}
                        </div>
                        <p className="mt-2 text-sm leading-6 text-slate-600">{scope.description}</p>
                      </button>
                    );
                  })}
                </div>
              </div>

              {status === 'success' && (
                <div className="rounded-[1.5rem] border border-emerald-200 bg-emerald-50 p-4 text-sm text-emerald-800">
                  Test alert sent. In the real integration, this would confirm the bot token and chat permissions.
                </div>
              )}
              {status === 'error' && (
                <div className="rounded-[1.5rem] border border-rose-200 bg-rose-50 p-4 text-sm text-rose-700">
                  Validation failed. Check your mock token length and chat ID format.
                </div>
              )}

              <div className="flex flex-col gap-3 border-t border-slate-200 pt-5 sm:flex-row sm:justify-end">
                <Button type="button" variant="ghost">
                  Save draft
                </Button>
                <Button type="submit" className="gap-2 bg-teal-900 hover:bg-teal-800" isLoading={isTesting}>
                  <Send className="h-4 w-4" />
                  Test connection
                </Button>
              </div>
            </form>
          </CardContent>
        </Card>

        <div className="space-y-6">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-xl">
                <Bot className="h-5 w-5 text-teal-700" />
                Delivery preview
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-4 text-sm text-slate-600">
              <div className="rounded-[1.5rem] border border-slate-200 bg-slate-50 p-4">
                <p className="font-semibold text-slate-900">Sample message</p>
                <p className="mt-3 text-sm leading-6">
                  `DOWN` Checkout Browser Flow failed in `us-east-1` with `assert_text` timeout after 30 seconds.
                </p>
              </div>
              <div className="rounded-[1.5rem] border border-slate-200 bg-slate-50 p-4">
                <p className="font-semibold text-slate-900">Current scopes</p>
                <p className="mt-3">{selectedAlerts.join(', ') || 'No alerts selected'}</p>
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-xl">
                <BellRing className="h-5 w-5 text-teal-700" />
                Platform notes
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-3 text-sm leading-6 text-slate-600">
              <InfoRow icon={Smartphone} text="PWA push is a future enhancement. Telegram acts as the first reliable alert channel." />
              <InfoRow icon={TriangleAlert} text="iOS web push requires iOS 16.4+ and an installed Home Screen app, even when Telegram is configured." />
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}

function InfoRow({ icon: Icon, text }: { icon: typeof Bot; text: string }) {
  return (
    <div className="rounded-[1.25rem] border border-slate-200 p-4">
      <div className="flex items-start gap-3">
        <div className="mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-2xl bg-teal-50 text-teal-700">
          <Icon className="h-4 w-4" />
        </div>
        <p>{text}</p>
      </div>
    </div>
  );
}
