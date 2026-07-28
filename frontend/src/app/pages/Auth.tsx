import { useMemo, useState } from 'react';
import { Link, useLocation, useNavigate } from 'react-router';
import { Activity, ShieldCheck, Users, Workflow } from 'lucide-react';
import { Button } from '../components/ui/Button';
import { Card, CardContent } from '../components/ui/Card';
import { Input } from '../components/ui/Input';
import { startSession } from '../auth';
import { ApiError, login, register, resendVerification } from '../api';
import { LanguageSwitcher, useTexts } from '../i18n';
import { useMeta } from '../meta-context';

const featureIcons = [Workflow, Users, ShieldCheck];

export default function AuthPage() {
  // страница — цель CTA с лендинга и прайса и тоже перечисляет возможности:
  // обещать здесь сценарии, которые вернут 403, нельзя
  const browserEnabled = useMeta()?.browser_monitors_enabled ?? false;
  const t = useTexts({
    ru: {
      features: [
        {
          title: 'Мониторинг из конфига',
          description:
            'UI и конфиг всегда синхронизированы: команда редактирует мониторы визуально и при этом может экспортировать источник истины.',
        },
        {
          title: 'Командное пространство',
          description:
            'Каждый оператор входит под своим аккаунтом и управляет мониторами своего рабочего пространства.',
        },
        {
          title: 'Готовность к PWA',
          description:
            'Установите дашборд, держите последние статусы в офлайн-кэше и подготовьтесь к push-уведомлениям.',
        },
      ],
      createAccount: 'Создать аккаунт',
      signIn: 'Войти',
      passwordsMismatch: 'Пароли не совпадают.',
      accountCreated:
        'Аккаунт создан. Подтвердите email, чтобы войти — мы только что отправили вам ссылку для подтверждения.',
      authFailed: 'Не удалось войти. Проверьте доступность бэкенда.',
      heroTitle: 'Управляйте мониторами от конфига до инцидента.',
      heroDescription:
        'Мониторинг сайтов на основе конфига: HTTP- и браузерные проверки, алерты в Telegram и устанавливаемый PWA-дашборд. Редактируйте мониторы визуально или загружайте YAML-конфиг — они всегда синхронизированы.',
      // вариант без упоминания сценариев — когда они выключены на инсталляции
      heroDescriptionHttpOnly:
        'Мониторинг сайтов на основе конфига: HTTP-проверки, алерты в Telegram и устанавливаемый PWA-дашборд. Редактируйте мониторы визуально или загружайте YAML-конфиг — они всегда синхронизированы.',
      registerKicker: 'Доступ к рабочему пространству',
      loginKicker: 'Вход для команды',
      registerDescription:
        'Создайте аккаунт, чтобы управлять мониторами, конфигами и алертами вашего рабочего пространства.',
      loginDescription:
        'Войдите с учётными данными рабочего пространства, чтобы открыть дашборд мониторинга.',
      emailLabel: 'Email',
      passwordLabel: 'Пароль',
      confirmPasswordLabel: 'Подтвердите пароль',
      forgotPassword: 'Забыли пароль?',
      verificationSent: 'Письмо с подтверждением отправлено.',
      sending: 'Отправляем...',
      resendVerification: 'Отправить письмо ещё раз',
      haveAccess: 'Уже есть доступ?',
      needAccount: 'Нужен аккаунт рабочего пространства?',
      createOne: 'Создать',
    },
    en: {
      features: [
        {
          title: 'Config-driven monitoring',
          description:
            'UI and config stay in sync, so teams can edit monitors visually and still export the source of truth.',
        },
        {
          title: 'Team workspace',
          description:
            'Every operator signs in with their own account and manages the monitors of their workspace.',
        },
        {
          title: 'PWA-ready operations',
          description:
            'Install the dashboard, keep recent status cached offline, and prepare for push notifications later.',
        },
      ],
      createAccount: 'Create account',
      signIn: 'Sign in',
      passwordsMismatch: 'Passwords do not match.',
      accountCreated:
        'Account created. Confirm your email to sign in — we just sent you a verification link.',
      authFailed: 'Unable to authenticate. Check backend availability.',
      heroTitle: 'Operate monitors from config to incident.',
      heroDescription:
        'Config-driven website monitoring with HTTP and browser checks, Telegram alerts, and an installable PWA dashboard. Edit monitors visually or upload a YAML config — both stay in sync.',
      heroDescriptionHttpOnly:
        'Config-driven website monitoring with HTTP checks, Telegram alerts, and an installable PWA dashboard. Edit monitors visually or upload a YAML config — both stay in sync.',
      registerKicker: 'Create workspace access',
      loginKicker: 'Team sign-in',
      registerDescription:
        'Create an account to manage monitors, configs, and alerts for your workspace.',
      loginDescription:
        'Sign in with your workspace credentials to reach the monitoring dashboard.',
      emailLabel: 'Email',
      passwordLabel: 'Password',
      confirmPasswordLabel: 'Confirm password',
      forgotPassword: 'Forgot password?',
      verificationSent: 'Verification email sent.',
      sending: 'Sending...',
      resendVerification: 'Resend verification email',
      haveAccess: 'Already have access?',
      needAccount: 'Need a workspace account?',
      createOne: 'Create one',
    },
  });
  const location = useLocation();
  const navigate = useNavigate();
  const isRegister = location.pathname === '/register';
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  // email, для которого требуется подтверждение (гейт вернул 403) — показываем resend
  const [pendingEmail, setPendingEmail] = useState<string | null>(null);
  const [resendState, setResendState] = useState<'idle' | 'sending' | 'sent'>('idle');

  const featureCopy = t.features.map((item, index) => ({ ...item, icon: featureIcons[index] }));

  const submitLabel = useMemo(
    () => (isRegister ? t.createAccount : t.signIn),
    [isRegister, t.createAccount, t.signIn]
  );

  const handleResend = async () => {
    if (!pendingEmail || resendState !== 'idle') return;
    setResendState('sending');
    try {
      await resendVerification(pendingEmail);
    } finally {
      setResendState('sent');
    }
  };

  const handleSubmit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setLoading(true);
    setError('');
    setPendingEmail(null);
    setResendState('idle');

    const formData = new FormData(event.currentTarget);
    const email = String(formData.get('email') ?? '');
    const password = String(formData.get('password') ?? '');

    if (isRegister) {
      const confirmPassword = String(formData.get('confirmPassword') ?? '');

      if (password !== confirmPassword) {
        setError(t.passwordsMismatch);
        setLoading(false);
        return;
      }
    }

    try {
      if (isRegister) {
        await register(email, password);
      }

      const token = await login(email, password);
      startSession(token.access_token, email, token.refresh_token);
      navigate('/');
    } catch (error) {
      // 403 на этой странице = требуется подтверждение email (после register или login)
      if (error instanceof ApiError && error.status === 403) {
        setPendingEmail(email);
        setError(isRegister ? t.accountCreated : error.message);
      } else {
        setError(error instanceof ApiError ? error.message : t.authFailed);
      }
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-background px-4 py-8 text-foreground">
      <div className="fixed right-4 top-4 z-50">
        <LanguageSwitcher />
      </div>
      <div className="mx-auto grid min-h-[calc(100vh-4rem)] max-w-6xl gap-8 lg:grid-cols-[1.15fr_0.85fr] lg:items-center">
        <section className="rounded-lg bg-card p-6 shadow-card md:p-10">
          <div className="mb-10 flex items-center gap-3">
            <div className="flex h-12 w-12 items-center justify-center rounded-lg bg-primary text-primary-foreground">
              <Activity className="h-6 w-6" />
            </div>
            <div>
              <p className="text-sm font-semibold text-primary">PWA Monitor</p>
              <h1 className="text-2xl font-semibold leading-8 text-foreground">
                {t.heroTitle}
              </h1>
            </div>
          </div>

          <p className="max-w-2xl text-base leading-6 text-muted-foreground">
            {browserEnabled ? t.heroDescription : t.heroDescriptionHttpOnly}
          </p>

          <div className="mt-8 grid gap-4 md:grid-cols-3">
            {featureCopy.map((item) => (
              <Card key={item.title} className="bg-secondary shadow-none">
                <CardContent className="space-y-3 p-5">
                  <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-accent text-primary">
                    <item.icon className="h-5 w-5" />
                  </div>
                  <div>
                    <h2 className="text-base font-semibold leading-6 text-foreground">{item.title}</h2>
                    <p className="mt-2 text-sm leading-5 text-muted-foreground">{item.description}</p>
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>
        </section>

        <Card className="overflow-hidden">
          <CardContent className="p-0">
            <div className="border-b border-border px-6 py-5">
              <p className="text-xs font-semibold text-primary">
                {isRegister ? t.registerKicker : t.loginKicker}
              </p>
              <h2 className="mt-2 text-lg font-semibold leading-6 text-foreground">{submitLabel}</h2>
              <p className="mt-2 text-sm leading-5 text-muted-foreground">
                {isRegister ? t.registerDescription : t.loginDescription}
              </p>
            </div>

            <form onSubmit={handleSubmit} className="space-y-5 p-6">
              <Input label={t.emailLabel} name="email" type="email" placeholder="operator@company.com" required />
              <Input
                label={t.passwordLabel}
                name="password"
                type="password"
                autoComplete={isRegister ? 'new-password' : 'current-password'}
                placeholder="••••••••"
                minLength={8}
                required
              />
              {!isRegister && (
                <div className="text-right">
                  <Link className="text-sm font-semibold text-primary hover:text-primary-hover" to="/forgot-password">
                    {t.forgotPassword}
                  </Link>
                </div>
              )}
              {isRegister && (
                <Input
                  label={t.confirmPasswordLabel}
                  name="confirmPassword"
                  type="password"
                  autoComplete="new-password"
                  placeholder="••••••••"
                  minLength={8}
                  required
                />
              )}

              {error && (
                <div className="rounded-lg bg-destructive/10 px-4 py-3 text-sm text-destructive">
                  {error}
                </div>
              )}

              {pendingEmail && (
                <div className="text-sm text-muted-foreground">
                  {resendState === 'sent' ? (
                    <span className="font-semibold text-primary">{t.verificationSent}</span>
                  ) : (
                    <button
                      type="button"
                      onClick={handleResend}
                      disabled={resendState === 'sending'}
                      className="font-semibold text-primary hover:text-primary-hover disabled:opacity-60"
                    >
                      {resendState === 'sending' ? t.sending : t.resendVerification}
                    </button>
                  )}
                </div>
              )}

              <Button type="submit" size="lg" className="w-full" isLoading={loading}>
                {submitLabel}
              </Button>
            </form>

            <div className="border-t border-border px-6 py-5 text-sm text-muted-foreground">
              {isRegister ? t.haveAccess : t.needAccount}{' '}
              <Link className="font-semibold text-primary hover:text-primary-hover" to={isRegister ? '/login' : '/register'}>
                {isRegister ? t.signIn : t.createOne}
              </Link>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
