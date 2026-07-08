import { useEffect, useState } from 'react';
import { NavLink, Outlet, useLocation, useNavigate } from 'react-router';
import {
  Activity,
  FileCode2,
  LayoutDashboard,
  LogOut,
  PlusCircle,
  Send,
  Smartphone,
} from 'lucide-react';
import { clearSession, getSessionEmail } from '../auth';
import { OfflineBanner } from '../components/OfflineBanner';
import { getMe } from '../api';
import { usePWA } from '../pwa/usePWA';
import { cn } from '../utils/cn';

const navigation = [
  { to: '/', label: 'Dashboard', icon: LayoutDashboard },
  { to: '/config', label: 'Config', icon: FileCode2 },
  { to: '/monitors/new', label: 'New Monitor', icon: PlusCircle },
  { to: '/telegram', label: 'Telegram', icon: Send },
];

export function AppLayout() {
  const navigate = useNavigate();
  const location = useLocation();
  const { isInstalled } = usePWA();
  const [isOffline, setIsOffline] = useState(() => typeof navigator !== 'undefined' && !navigator.onLine);
  const [email, setEmail] = useState(() => getSessionEmail() ?? '');
  const [orgName, setOrgName] = useState('My team');

  useEffect(() => {
    let ignore = false;

    getMe()
      .then((user) => {
        if (!ignore) {
          setEmail(user.email);
          setOrgName(user.organization?.name ?? 'My team');
        }
      })
      .catch(() => {
        // Keep the session email fallback when /auth/me is unavailable.
      });

    return () => {
      ignore = true;
    };
  }, []);

  useEffect(() => {
    const onOnline = () => setIsOffline(false);
    const onOffline = () => setIsOffline(true);

    window.addEventListener('online', onOnline);
    window.addEventListener('offline', onOffline);

    return () => {
      window.removeEventListener('online', onOnline);
      window.removeEventListener('offline', onOffline);
    };
  }, []);

  const handleLogout = () => {
    clearSession();
    navigate('/login');
  };

  const currentSection = navigation.find((item) =>
    item.to === '/' ? location.pathname === '/' : location.pathname.startsWith(item.to)
  );

  return (
    <div className="min-h-screen bg-background">
      {isOffline && <OfflineBanner />}

      <div className="mx-auto flex min-h-screen max-w-[1600px]">
        <aside className="sticky top-0 hidden h-screen w-72 shrink-0 bg-card px-4 py-6 shadow-card lg:flex lg:flex-col">
          <div className="flex items-center gap-3 px-2">
            <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-accent text-primary">
              <Activity className="h-6 w-6" />
            </div>
            <div>
              <p className="text-lg font-semibold text-foreground">Uplynx Console</p>
              <p className="text-xs text-placeholder">Monitoring ops</p>
            </div>
          </div>

          <div className="mt-6 rounded-lg bg-secondary p-4">
            <p className="text-xs text-placeholder">Active workspace</p>
            <p className="mt-1 text-sm font-semibold text-foreground">{orgName}</p>
            <p className="mt-0.5 truncate text-xs text-muted-foreground">{email || 'Signed in'}</p>
            <div className="mt-3 flex flex-wrap gap-2">
              <span className="rounded-lg bg-accent px-2.5 py-1 text-xs font-semibold text-primary">
                {isInstalled ? 'PWA installed' : 'Browser mode'}
              </span>
            </div>
          </div>

          <nav className="mt-6 space-y-1">
            {navigation.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                className={({ isActive }) =>
                  cn(
                    'flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium transition-colors',
                    isActive ? 'bg-accent text-primary' : 'text-foreground hover:text-primary'
                  )
                }
              >
                <item.icon className="h-5 w-5" />
                {item.label}
              </NavLink>
            ))}
          </nav>

          <button
            type="button"
            onClick={handleLogout}
            className="mt-auto flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium text-muted-foreground transition-colors hover:text-destructive"
          >
            <LogOut className="h-5 w-5" />
            Sign out
          </button>
        </aside>

        <main className="flex min-h-screen min-w-0 flex-1 flex-col">
          <header className="sticky top-0 z-40 h-[60px] border-b border-border bg-background px-4 md:px-6">
            <div className="mx-auto flex h-full max-w-7xl items-center justify-between gap-4">
              <div className="min-w-0">
                <h1 className="truncate text-lg font-semibold leading-6 text-foreground">
                  {currentSection?.label === 'Dashboard'
                    ? 'Fleet overview'
                    : currentSection?.label ?? 'Monitoring workspace'}
                </h1>
              </div>

              <div className="flex items-center gap-3">
                <div className="hidden rounded-lg bg-card px-3 py-1.5 text-xs font-medium text-muted-foreground shadow-card md:flex md:items-center md:gap-2">
                  <Smartphone className="h-3.5 w-3.5 text-primary" />
                  {isInstalled ? 'Installed PWA' : 'Install available'}
                </div>
                <div className="flex items-center gap-3">
                  <div className="flex h-8 w-8 items-center justify-center rounded-full bg-border text-sm font-semibold text-muted-foreground">
                    {(email[0] ?? '?').toUpperCase()}
                  </div>
                  <div className="hidden min-w-0 md:block">
                    <p className="max-w-[14rem] truncate text-sm leading-5 text-foreground">{email || 'Operator'}</p>
                    <p className="text-xs leading-4 text-placeholder">{orgName}</p>
                  </div>
                </div>
              </div>
            </div>
          </header>

          <div className="mx-auto w-full max-w-7xl flex-1 px-4 py-6 md:px-6 md:py-8 pb-[calc(5.5rem+env(safe-area-inset-bottom))] lg:pb-8">
            <Outlet />
          </div>
        </main>
      </div>

      <nav className="fixed inset-x-0 bottom-0 z-50 border-t border-border bg-card px-2 pb-[env(safe-area-inset-bottom)] pt-2 shadow-bottom-sheet lg:hidden">
        <div className="grid grid-cols-4 gap-1">
          {navigation.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              className={({ isActive }) =>
                cn(
                  'flex min-h-14 flex-col items-center justify-center rounded-lg gap-1 text-[11px] font-semibold transition-colors',
                  isActive ? 'bg-accent text-primary' : 'text-placeholder'
                )
              }
            >
              <item.icon className="h-4.5 w-4.5" />
              <span>{item.label}</span>
            </NavLink>
          ))}
        </div>
      </nav>
    </div>
  );
}
