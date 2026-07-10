import { useState } from 'react';
import { Link } from 'react-router';
import { Activity } from 'lucide-react';
import { Button } from '../components/ui/Button';
import { Card, CardContent } from '../components/ui/Card';
import { Input } from '../components/ui/Input';
import { ApiError, forgotPassword } from '../api';
import { useTexts } from '../i18n';

export default function ForgotPasswordPage() {
  const t = useTexts({
    ru: {
      title: 'Сброс пароля',
      description: 'Укажите email, с которым вы регистрировались, и мы пришлём ссылку для установки нового пароля.',
      requestFailed: 'Не удалось запросить ссылку для сброса. Проверьте доступность бэкенда.',
      sentNotice: 'Если такой аккаунт существует, мы отправили ссылку для сброса. Проверьте почту.',
      backToSignIn: 'Вернуться ко входу',
      emailLabel: 'Email',
      sendLink: 'Отправить ссылку',
      remembered: 'Вспомнили пароль?',
      signIn: 'Войти',
    },
    en: {
      title: 'Reset your password',
      description: 'Enter the email you signed up with and we will send you a link to set a new password.',
      requestFailed: 'Unable to request a reset link. Check backend availability.',
      sentNotice: 'If that account exists, we sent a reset link. Check your inbox.',
      backToSignIn: 'Back to sign in',
      emailLabel: 'Email',
      sendLink: 'Send reset link',
      remembered: 'Remembered it?',
      signIn: 'Sign in',
    },
  });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [submitted, setSubmitted] = useState(false);

  const handleSubmit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setLoading(true);
    setError('');

    const formData = new FormData(event.currentTarget);
    const email = String(formData.get('email') ?? '');

    try {
      await forgotPassword(email);
      setSubmitted(true);
    } catch (error) {
      setError(error instanceof ApiError ? error.message : t.requestFailed);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex min-h-screen items-center justify-center bg-background px-4 py-8 text-foreground">
      <Card className="w-full max-w-md overflow-hidden">
        <CardContent className="p-0">
          <div className="border-b border-border px-6 py-5">
            <div className="flex items-center gap-3">
              <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-primary text-primary-foreground">
                <Activity className="h-5 w-5" />
              </div>
              <div>
                <p className="text-xs font-semibold text-primary">PWA Monitor</p>
                <h1 className="text-lg font-semibold leading-6 text-foreground">{t.title}</h1>
              </div>
            </div>
            <p className="mt-3 text-sm leading-5 text-muted-foreground">
              {t.description}
            </p>
          </div>

          {submitted ? (
            <div className="space-y-5 p-6">
              <div className="rounded-lg bg-accent px-4 py-3 text-sm text-accent-foreground">
                {t.sentNotice}
              </div>
              <Link className="text-sm font-semibold text-primary hover:text-primary-hover" to="/login">
                {t.backToSignIn}
              </Link>
            </div>
          ) : (
            <form onSubmit={handleSubmit} className="space-y-5 p-6">
              <Input label={t.emailLabel} name="email" type="email" placeholder="operator@company.com" required />

              {error && (
                <div className="rounded-lg bg-destructive/10 px-4 py-3 text-sm text-destructive">
                  {error}
                </div>
              )}

              <Button type="submit" size="lg" className="w-full" isLoading={loading}>
                {t.sendLink}
              </Button>

              <div className="text-sm text-muted-foreground">
                {t.remembered}{' '}
                <Link className="font-semibold text-primary hover:text-primary-hover" to="/login">
                  {t.signIn}
                </Link>
              </div>
            </form>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
