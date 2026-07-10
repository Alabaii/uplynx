import { useEffect, useState } from 'react';
import { Bell, BellRing, Bot, CheckCircle2, Mail, Send, Smartphone, TriangleAlert } from 'lucide-react';
import { Button } from '../components/ui/Button';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/Card';
import { Input } from '../components/ui/Input';
import { ApiError, connectTelegram, getMe, getTelegram, listOrgs, testTelegram, updateCurrentOrg } from '../api';
import { useMeta } from '../meta-context';
import { usePushNotifications, type PushStatus } from '../pwa/usePushNotifications';
import { cn } from '../utils/cn';
import { useTexts } from '../i18n';

const alertScopeIds = ['down', 'degraded', 'recovered', 'ssl'] as const;

type AlertScope = (typeof alertScopeIds)[number];

export default function TelegramSettings() {
  const t = useTexts({
    ru: {
      integration: 'Интеграция с Telegram',
      title: 'Доставляйте инциденты операторам',
      description: 'Подключите Telegram-бота, чтобы получать алерты, когда мониторы падают, деградируют или восстанавливаются.',
      connectedToChat: (chat: string) => `Подключено к чату ${chat || 'неизвестно'}`,
      notConnected: 'Ещё не подключено',
      configureBot: 'Настройка бота',
      botToken: 'Токен бота',
      chatId: 'ID чата',
      alertScope: 'Область алертов',
      scopes: {
        down: { label: 'Падение', description: 'Критические сбои и таймауты' },
        degraded: { label: 'Деградация', description: 'Медленные, но не полностью сломанные проверки' },
        recovered: { label: 'Восстановление', description: 'Сигнал, когда статус возвращается в зелёную зону' },
        ssl: { label: 'SSL', description: 'TLS-сертификат истекает через 30/14/7/1 дней' },
      },
      saved: 'Настройки Telegram сохранены.',
      saveError: 'Не удалось сохранить настройки Telegram.',
      testSent: 'Тестовый алерт отправлен. Проверьте чат в Telegram.',
      testError: 'Не удалось отправить тестовое сообщение.',
      testConnection: 'Проверить подключение',
      saveSettings: 'Сохранить настройки',
      deliveryPreview: 'Предпросмотр доставки',
      sampleMessage: 'Пример сообщения',
      sampleText: '`DOWN` Монитор `api-health` упал: HTTP 500 после 3 повторов.',
      currentScopes: 'Текущие области',
      noAlertsSelected: 'Алерты не выбраны',
      platformNotes: 'Заметки о платформе',
      noteChannels: 'Браузерный push и Telegram — независимые каналы: включите любой из них или оба.',
      noteIos: 'Web-push на iOS требует iOS 16.4+ и установленного на домашний экран приложения, даже если Telegram настроен.',
    },
    en: {
      integration: 'Telegram integration',
      title: 'Route incidents to operators',
      description: 'Connect a Telegram bot to receive alerts when monitors go down, degrade, or recover.',
      connectedToChat: (chat: string) => `Connected to chat ${chat || 'unknown'}`,
      notConnected: 'Not connected yet',
      configureBot: 'Configure bot',
      botToken: 'Bot token',
      chatId: 'Chat ID',
      alertScope: 'Alert scope',
      scopes: {
        down: { label: 'Down', description: 'Critical failures and timeouts' },
        degraded: { label: 'Degraded', description: 'Slow but not fully broken checks' },
        recovered: { label: 'Recovered', description: 'Follow-up signal when status returns to green' },
        ssl: { label: 'SSL expiry', description: 'TLS certificate expires in 30/14/7/1 days' },
      },
      saved: 'Telegram settings saved.',
      saveError: 'Unable to save Telegram settings.',
      testSent: 'Test alert sent. Check your Telegram chat.',
      testError: 'Unable to send a test message.',
      testConnection: 'Test connection',
      saveSettings: 'Save settings',
      deliveryPreview: 'Delivery preview',
      sampleMessage: 'Sample message',
      sampleText: '`DOWN` Monitor `api-health` failed: HTTP 500 after 3 retries.',
      currentScopes: 'Current scopes',
      noAlertsSelected: 'No alerts selected',
      platformNotes: 'Platform notes',
      noteChannels: 'Browser push and Telegram are independent channels - enable either or both.',
      noteIos: 'iOS web push requires iOS 16.4+ and an installed Home Screen app, even when Telegram is configured.',
    },
  });

  const alertScopes = alertScopeIds.map((id) => ({ id, ...t.scopes[id] }));

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
            alertScopeIds.some((id) => id === scope)
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
      setMessage({ tone: 'success', text: t.saved });
    } catch (error) {
      setMessage({
        tone: 'error',
        text: error instanceof ApiError ? error.message : t.saveError,
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
          ? { tone: 'success', text: t.testSent }
          : { tone: 'error', text: result.detail }
      );
    } catch (error) {
      setMessage({
        tone: 'error',
        text: error instanceof ApiError ? error.message : t.testError,
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
            <p className="text-sm font-semibold text-primary">{t.integration}</p>
            <h1 className="mt-2 text-2xl font-semibold leading-8 text-foreground">{t.title}</h1>
            <p className="mt-3 max-w-3xl text-sm leading-5 text-muted-foreground">
              {t.description}
            </p>
          </div>

          {connected ? (
            <div className="rounded-lg bg-accent px-4 py-3 text-sm text-accent-foreground">
              {t.connectedToChat(chatId)}
            </div>
          ) : (
            <div className="rounded-lg bg-secondary px-4 py-3 text-sm text-muted-foreground">
              {t.notConnected}
            </div>
          )}
        </div>
      </section>

      <div className="grid gap-6 xl:grid-cols-[1fr_0.9fr]">
        <Card className="overflow-hidden">
          <CardHeader className="border-b border-border">
            <CardTitle className="flex items-center gap-2">
              <Send className="h-5 w-5 text-primary" />
              {t.configureBot}
            </CardTitle>
          </CardHeader>

          <CardContent className="p-6">
            <form onSubmit={handleSave} className="space-y-6">
              <div className="grid gap-4">
                <Input
                  label={t.botToken}
                  type="password"
                  value={token}
                  onChange={(event) => setToken(event.target.value)}
                  placeholder={maskedToken || '123456789:AA...'}
                  required
                />
                <Input
                  label={t.chatId}
                  value={chatId}
                  onChange={(event) => setChatId(event.target.value)}
                  placeholder="-1001234567890"
                  required
                />
              </div>

              <div className="space-y-3">
                <p className="text-sm font-semibold text-foreground">{t.alertScope}</p>
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
                  {t.testConnection}
                </Button>
                <Button type="submit" isLoading={isSaving}>
                  <Send className="h-4 w-4" />
                  {t.saveSettings}
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
                {t.deliveryPreview}
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-4 text-sm text-muted-foreground">
              <div className="rounded-lg bg-secondary p-4">
                <p className="font-semibold text-foreground">{t.sampleMessage}</p>
                <p className="mt-3 text-sm leading-5">
                  {t.sampleText}
                </p>
              </div>
              <div className="rounded-lg bg-secondary p-4">
                <p className="font-semibold text-foreground">{t.currentScopes}</p>
                <p className="mt-3">{selectedAlerts.join(', ') || t.noAlertsSelected}</p>
              </div>
            </CardContent>
          </Card>

          <BrowserPushCard />

          <EmailAlertsCard />

          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <BellRing className="h-5 w-5 text-primary" />
                {t.platformNotes}
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-3 text-sm leading-5 text-muted-foreground">
              <InfoRow icon={Smartphone} text={t.noteChannels} />
              <InfoRow icon={TriangleAlert} text={t.noteIos} />
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}

function BrowserPushCard() {
  const t = useTexts({
    ru: {
      browserPush: 'Браузерный push',
      status: 'Статус',
      enabledOnDevice: 'Включено на этом устройстве',
      notActive: 'Не активно',
      on: 'Вкл',
      off: 'Выкл',
      statusText: {
        loading: 'Проверяем поддержку браузера...',
        unsupported: 'Для push нужно установленное PWA (production-сборка). Откройте приложение с домашнего экрана, чтобы включить его.',
        'disabled-on-server': 'Push не настроен на этом сервере. Попросите администратора задать VAPID-ключи.',
        'permission-denied': 'Уведомления для этого сайта заблокированы. Разрешите их в настройках браузера и перезагрузите страницу.',
        subscribed: 'Это устройство получает push-алерты при смене статуса мониторов.',
        'not-subscribed': 'Это устройство ещё не подписано. Включите push, чтобы получать алерты, даже когда приложение закрыто.',
      } as Record<PushStatus, string>,
      disablePush: 'Отключить push',
      enablePush: 'Включить push',
    },
    en: {
      browserPush: 'Browser push',
      status: 'Status',
      enabledOnDevice: 'Enabled on this device',
      notActive: 'Not active',
      on: 'On',
      off: 'Off',
      statusText: {
        loading: 'Checking browser support...',
        unsupported: 'Push requires the installed PWA (production build). Open the app from your home screen to enable it.',
        'disabled-on-server': 'Push is not configured on this server. Ask an administrator to set VAPID keys.',
        'permission-denied': 'Notifications are blocked for this site. Allow them in the browser settings and reload.',
        subscribed: 'This device receives push alerts when monitors change status.',
        'not-subscribed': 'This device is not subscribed yet. Enable push to get alerts even when the app is closed.',
      } as Record<PushStatus, string>,
      disablePush: 'Disable push',
      enablePush: 'Enable push',
    },
  });

  const { status, isBusy, error, enable, disable } = usePushNotifications();
  const canToggle = status === 'subscribed' || status === 'not-subscribed';

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Bell className="h-5 w-5 text-primary" />
          {t.browserPush}
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4 text-sm leading-5 text-muted-foreground">
        <div className="flex items-center justify-between gap-3 rounded-lg bg-secondary p-4">
          <div>
            <p className="font-semibold text-foreground">{t.status}</p>
            <p className="mt-1">{status === 'subscribed' ? t.enabledOnDevice : t.notActive}</p>
          </div>
          <span
            className={cn(
              'rounded-lg px-3 py-1 text-xs font-semibold',
              status === 'subscribed' ? 'bg-accent text-accent-foreground' : 'bg-card text-muted-foreground'
            )}
          >
            {status === 'subscribed' ? t.on : t.off}
          </span>
        </div>

        <p>{t.statusText[status]}</p>

        {error && <p className="rounded-lg bg-destructive/10 p-3 text-destructive">{error}</p>}

        {canToggle && (
          <Button
            type="button"
            variant={status === 'subscribed' ? 'ghost' : 'primary'}
            onClick={status === 'subscribed' ? disable : enable}
            isLoading={isBusy}
          >
            <Bell className="h-4 w-4" />
            {status === 'subscribed' ? t.disablePush : t.enablePush}
          </Button>
        )}
      </CardContent>
    </Card>
  );
}

function EmailAlertsCard() {
  const t = useTexts({
    ru: {
      emailAlerts: 'Email-алерты',
      smtpNotice: 'Email не настроен на этом сервере (SMTP_HOST). Получатели сохраняются, но письма не отправляются.',
      recipientsLabel: 'Получатели (через запятую, до 10)',
      saved: 'Получатели email сохранены.',
      saveError: 'Не удалось сохранить получателей email.',
      saveRecipients: 'Сохранить получателей',
      recipients: 'Получатели',
      noRecipients: 'Получатели не настроены. Попросите владельца рабочего пространства добавить их.',
    },
    en: {
      emailAlerts: 'Email alerts',
      smtpNotice: 'Email is not configured on this server (SMTP_HOST). Recipients are stored, but no emails are sent.',
      recipientsLabel: 'Recipients (comma-separated, up to 10)',
      saved: 'Email recipients saved.',
      saveError: 'Unable to save email recipients.',
      saveRecipients: 'Save recipients',
      recipients: 'Recipients',
      noRecipients: 'No recipients configured. Ask the workspace owner to add some.',
    },
  });

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
      setMessage({ tone: 'success', text: t.saved });
    } catch (error) {
      setMessage({
        tone: 'error',
        text: error instanceof ApiError ? error.message : t.saveError,
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
          {t.emailAlerts}
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4 text-sm leading-5 text-muted-foreground">
        {!emailEnabled && (
          <p className="rounded-lg bg-secondary p-4">
            {t.smtpNotice}
          </p>
        )}

        {isOwner ? (
          <form onSubmit={handleSave} className="space-y-4">
            <div>
              <label htmlFor="alert-emails" className="mb-1 block text-sm font-normal text-placeholder">
                {t.recipientsLabel}
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
                {t.saveRecipients}
              </Button>
            </div>
          </form>
        ) : (
          <div className="rounded-lg bg-secondary p-4">
            <p className="font-semibold text-foreground">{t.recipients}</p>
            <p className="mt-2">
              {emails.length
                ? emails.join(', ')
                : t.noRecipients}
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
