import { useMemo, useState } from 'react';
import { Link, useLocation, useNavigate } from 'react-router';
import { Activity, ShieldCheck, Users, Workflow } from 'lucide-react';
import { Button } from '../components/ui/Button';
import { Card, CardContent } from '../components/ui/Card';
import { Input } from '../components/ui/Input';
import { createSession } from '../auth';
import { ApiError, login, register } from '../api';

const featureCopy = [
  {
    icon: Workflow,
    title: 'Config-driven monitoring',
    description: 'UI and config stay in sync, so teams can edit monitors visually and still export the source of truth.',
  },
  {
    icon: Users,
    title: 'Team workspace',
    description: 'Every operator signs in with their own account and manages the monitors of their workspace.',
  },
  {
    icon: ShieldCheck,
    title: 'PWA-ready operations',
    description: 'Install the dashboard, keep recent status cached offline, and prepare for push notifications later.',
  },
];

export default function AuthPage() {
  const location = useLocation();
  const navigate = useNavigate();
  const isRegister = location.pathname === '/register';
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const submitLabel = useMemo(() => (isRegister ? 'Create account' : 'Sign in'), [isRegister]);

  const handleSubmit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setLoading(true);
    setError('');

    const formData = new FormData(event.currentTarget);
    const email = String(formData.get('email') ?? '');
    const password = String(formData.get('password') ?? '');

    if (isRegister) {
      const confirmPassword = String(formData.get('confirmPassword') ?? '');

      if (password !== confirmPassword) {
        setError('Passwords do not match.');
        setLoading(false);
        return;
      }
    }

    try {
      if (isRegister) {
        await register(email, password);
      }

      const token = await login(email, password);
      createSession(token.access_token, email);
      navigate('/');
    } catch (error) {
      setError(error instanceof ApiError ? error.message : 'Unable to authenticate. Check backend availability.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-background px-4 py-8 text-foreground">
      <div className="mx-auto grid min-h-[calc(100vh-4rem)] max-w-6xl gap-8 lg:grid-cols-[1.15fr_0.85fr] lg:items-center">
        <section className="rounded-lg bg-card p-6 shadow-card md:p-10">
          <div className="mb-10 flex items-center gap-3">
            <div className="flex h-12 w-12 items-center justify-center rounded-lg bg-primary text-primary-foreground">
              <Activity className="h-6 w-6" />
            </div>
            <div>
              <p className="text-sm font-semibold text-primary">PWA Monitor</p>
              <h1 className="text-2xl font-semibold leading-8 text-foreground">
                Operate monitors from config to incident.
              </h1>
            </div>
          </div>

          <p className="max-w-2xl text-base leading-6 text-muted-foreground">
            Config-driven website monitoring with HTTP and browser checks, Telegram alerts, and an installable
            PWA dashboard. Edit monitors visually or upload a YAML config — both stay in sync.
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
                {isRegister ? 'Create workspace access' : 'Team sign-in'}
              </p>
              <h2 className="mt-2 text-lg font-semibold leading-6 text-foreground">{submitLabel}</h2>
              <p className="mt-2 text-sm leading-5 text-muted-foreground">
                {isRegister
                  ? 'Create an account to manage monitors, configs, and alerts for your workspace.'
                  : 'Sign in with your workspace credentials to reach the monitoring dashboard.'}
              </p>
            </div>

            <form onSubmit={handleSubmit} className="space-y-5 p-6">
              <Input label="Email" name="email" type="email" placeholder="operator@company.com" required />
              <Input
                label="Password"
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
                    Forgot password?
                  </Link>
                </div>
              )}
              {isRegister && (
                <Input
                  label="Confirm password"
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

              <Button type="submit" size="lg" className="w-full" isLoading={loading}>
                {submitLabel}
              </Button>
            </form>

            <div className="border-t border-border px-6 py-5 text-sm text-muted-foreground">
              {isRegister ? 'Already have access?' : 'Need a workspace account?'}{' '}
              <Link className="font-semibold text-primary hover:text-primary-hover" to={isRegister ? '/login' : '/register'}>
                {isRegister ? 'Sign in' : 'Create one'}
              </Link>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
