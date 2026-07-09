import { useState } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router';
import { Activity } from 'lucide-react';
import { Button } from '../components/ui/Button';
import { Card, CardContent } from '../components/ui/Card';
import { Input } from '../components/ui/Input';
import { ApiError, resetPassword } from '../api';
import { useTexts } from '../i18n';

export default function ResetPasswordPage() {
  const t = useTexts({
    ru: {
      title: 'Придумайте новый пароль',
      passwordsMismatch: 'Пароли не совпадают.',
      resetFailed: 'Не удалось сбросить пароль. Проверьте доступность бэкенда.',
      invalidLink: 'Ссылка для сброса недействительна или неполная.',
      requestNewLink: 'Запросить новую ссылку',
      updated: 'Пароль обновлён. Войдите с новым паролем.',
      goToSignIn: 'Перейти ко входу',
      newPasswordLabel: 'Новый пароль',
      confirmPasswordLabel: 'Подтвердите пароль',
      setNewPassword: 'Установить новый пароль',
    },
    en: {
      title: 'Choose a new password',
      passwordsMismatch: 'Passwords do not match.',
      resetFailed: 'Unable to reset the password. Check backend availability.',
      invalidLink: 'The reset link is invalid or incomplete.',
      requestNewLink: 'Request a new reset link',
      updated: 'Your password has been updated. Sign in with the new password.',
      goToSignIn: 'Go to sign in',
      newPasswordLabel: 'New password',
      confirmPasswordLabel: 'Confirm password',
      setNewPassword: 'Set new password',
    },
  });
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const token = searchParams.get('token') ?? '';
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [done, setDone] = useState(false);

  const handleSubmit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setError('');

    const formData = new FormData(event.currentTarget);
    const password = String(formData.get('password') ?? '');
    const confirmPassword = String(formData.get('confirmPassword') ?? '');

    if (password !== confirmPassword) {
      setError(t.passwordsMismatch);
      return;
    }

    setLoading(true);

    try {
      await resetPassword(token, password);
      setDone(true);
    } catch (error) {
      setError(error instanceof ApiError ? error.message : t.resetFailed);
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
          </div>

          {!token ? (
            <div className="space-y-5 p-6">
              <div className="rounded-lg bg-destructive/10 px-4 py-3 text-sm text-destructive">
                {t.invalidLink}
              </div>
              <Link className="text-sm font-semibold text-primary hover:text-primary-hover" to="/forgot-password">
                {t.requestNewLink}
              </Link>
            </div>
          ) : done ? (
            <div className="space-y-5 p-6">
              <div className="rounded-lg bg-accent px-4 py-3 text-sm text-accent-foreground">
                {t.updated}
              </div>
              <Button type="button" size="lg" className="w-full" onClick={() => navigate('/login')}>
                {t.goToSignIn}
              </Button>
            </div>
          ) : (
            <form onSubmit={handleSubmit} className="space-y-5 p-6">
              <Input
                label={t.newPasswordLabel}
                name="password"
                type="password"
                autoComplete="new-password"
                placeholder="••••••••"
                minLength={8}
                required
              />
              <Input
                label={t.confirmPasswordLabel}
                name="confirmPassword"
                type="password"
                autoComplete="new-password"
                placeholder="••••••••"
                minLength={8}
                required
              />

              {error && (
                <div className="rounded-lg bg-destructive/10 px-4 py-3 text-sm text-destructive">
                  {error}
                </div>
              )}

              <Button type="submit" size="lg" className="w-full" isLoading={loading}>
                {t.setNewPassword}
              </Button>
            </form>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
