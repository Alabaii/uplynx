import { useMemo, useState } from 'react';
import { Link, useLocation, useNavigate } from 'react-router';
import { Activity, ShieldCheck, Users, Workflow } from 'lucide-react';
import { Button } from '../components/ui/Button';
import { Card, CardContent } from '../components/ui/Card';
import { Input } from '../components/ui/Input';
import { createMockSession } from '../auth';

const featureCopy = [
  {
    icon: Workflow,
    title: 'Config-driven monitoring',
    description: 'UI and config stay in sync, so teams can edit monitors visually and still export the source of truth.',
  },
  {
    icon: Users,
    title: 'Per-user and group access',
    description: 'Each operator works inside their own workspace with shared monitors available through group membership.',
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

  const submitLabel = useMemo(() => (isRegister ? 'Create account' : 'Sign in'), [isRegister]);

  const handleSubmit = (event: React.FormEvent) => {
    event.preventDefault();
    setLoading(true);

    window.setTimeout(() => {
      createMockSession();
      navigate('/');
      setLoading(false);
    }, 900);
  };

  return (
    <div className="min-h-screen bg-[radial-gradient(circle_at_top_left,_rgba(15,118,110,0.18),_transparent_28%),linear-gradient(180deg,_#f5f9f7_0%,_#edf3ef_40%,_#f8fafc_100%)] px-4 py-8 text-slate-900">
      <div className="mx-auto grid min-h-[calc(100vh-4rem)] max-w-6xl gap-8 lg:grid-cols-[1.15fr_0.85fr] lg:items-center">
        <section className="rounded-[2rem] border border-white/70 bg-white/70 p-6 shadow-[0_24px_80px_rgba(15,23,42,0.08)] backdrop-blur md:p-10">
          <div className="mb-10 flex items-center gap-3">
            <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-teal-900 text-white shadow-lg shadow-teal-900/20">
              <Activity className="h-6 w-6" />
            </div>
            <div>
              <p className="text-sm font-semibold uppercase tracking-[0.24em] text-teal-700">PWA Monitor</p>
              <h1 className="text-3xl font-semibold tracking-tight text-slate-950 md:text-5xl">
                Operate monitors from config to incident.
              </h1>
            </div>
          </div>

          <p className="max-w-2xl text-base leading-7 text-slate-600 md:text-lg">
            A mock product shell for config-driven website monitoring. The UX already reflects per-user configs,
            browser scenarios, Telegram alerts, and PWA-first operations even before the backend arrives.
          </p>

          <div className="mt-8 grid gap-4 md:grid-cols-3">
            {featureCopy.map((item) => (
              <Card key={item.title} className="border-white/70 bg-white/80 shadow-none">
                <CardContent className="space-y-3 p-5">
                  <div className="flex h-10 w-10 items-center justify-center rounded-2xl bg-teal-50 text-teal-700">
                    <item.icon className="h-5 w-5" />
                  </div>
                  <div>
                    <h2 className="text-base font-semibold text-slate-900">{item.title}</h2>
                    <p className="mt-2 text-sm leading-6 text-slate-600">{item.description}</p>
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>
        </section>

        <Card className="overflow-hidden border-slate-200/80 bg-white/90 shadow-[0_24px_80px_rgba(15,23,42,0.08)]">
          <CardContent className="p-0">
            <div className="border-b border-slate-200 bg-slate-50/80 px-6 py-5">
              <p className="text-xs font-semibold uppercase tracking-[0.24em] text-teal-700">
                {isRegister ? 'Create workspace access' : 'Team sign-in'}
              </p>
              <h2 className="mt-2 text-2xl font-semibold text-slate-950">{submitLabel}</h2>
              <p className="mt-2 text-sm leading-6 text-slate-600">
                {isRegister
                  ? 'Create a mock account to manage your own config and collaborate through shared groups.'
                  : 'Enter any credentials to access the UI prototype. Session state stays local to this browser.'}
              </p>
            </div>

            <form onSubmit={handleSubmit} className="space-y-5 p-6">
              {isRegister && <Input label="Full name" placeholder="Julia Dovzhenko" required />}
              <Input label="Email" type="email" placeholder="operator@company.com" required />
              <Input
                label="Password"
                type="password"
                autoComplete={isRegister ? 'new-password' : 'current-password'}
                placeholder="••••••••"
                required
              />
              {isRegister && (
                <Input
                  label="Confirm password"
                  type="password"
                  autoComplete="new-password"
                  placeholder="••••••••"
                  required
                />
              )}

              <div className="rounded-2xl border border-slate-200 bg-slate-50 px-4 py-3 text-xs leading-5 text-slate-600">
                Mock auth note: no real JWT yet. This flow only creates a local session so we can validate routing,
                role-aware copy, and protected screens.
              </div>

              <Button type="submit" className="h-11 w-full bg-teal-900 hover:bg-teal-800" isLoading={loading}>
                {submitLabel}
              </Button>
            </form>

            <div className="border-t border-slate-200 px-6 py-5 text-sm text-slate-600">
              {isRegister ? 'Already have access?' : 'Need a workspace account?'}{' '}
              <Link className="font-semibold text-teal-800 hover:text-teal-700" to={isRegister ? '/login' : '/register'}>
                {isRegister ? 'Sign in' : 'Create one'}
              </Link>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
