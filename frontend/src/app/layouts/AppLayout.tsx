import { useEffect, useState } from 'react';
import { NavLink, Outlet, useLocation, useNavigate } from 'react-router';
import {
  Activity,
  BellRing,
  FileCode2,
  LayoutDashboard,
  LogOut,
  PlusCircle,
  Send,
  Smartphone,
} from 'lucide-react';
import { clearSession } from '../auth';
import { OfflineBanner } from '../components/OfflineBanner';
import { getActiveGroup, getCurrentUser } from '../data/mockMonitoring';
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
  const user = getCurrentUser();
  const activeGroup = getActiveGroup();
  const { isInstalled } = usePWA();
  const [isOffline, setIsOffline] = useState(() => typeof navigator !== 'undefined' && !navigator.onLine);

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
    <div className="min-h-screen bg-[linear-gradient(180deg,_#f4f7f6_0%,_#eef3f0_42%,_#f8fafc_100%)]">
      {isOffline && <OfflineBanner />}

      <div className="mx-auto flex min-h-screen max-w-[1600px]">
        <aside className="sticky top-0 hidden h-screen w-80 shrink-0 border-r border-white/70 bg-slate-950 px-6 py-6 text-slate-100 lg:flex lg:flex-col">
          <div className="flex items-center gap-3">
            <div className="flex h-12 w-12 items-center justify-center rounded-2xl bg-teal-500/15 text-teal-300">
              <Activity className="h-6 w-6" />
            </div>
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.24em] text-teal-300/80">Monitoring ops</p>
              <p className="text-xl font-semibold tracking-tight text-white">Uplynx Console</p>
            </div>
          </div>

          <div className="mt-8 rounded-[1.5rem] border border-white/10 bg-white/5 p-4">
            <p className="text-xs uppercase tracking-[0.22em] text-slate-400">Active workspace</p>
            <p className="mt-2 text-lg font-semibold text-white">{activeGroup.name}</p>
            <p className="mt-1 text-sm text-slate-300">{user.email}</p>
            <div className="mt-4 flex flex-wrap gap-2">
              <span className="rounded-full bg-emerald-500/15 px-3 py-1 text-xs font-semibold text-emerald-300">
                {activeGroup.role}
              </span>
              <span className="rounded-full bg-cyan-500/15 px-3 py-1 text-xs font-semibold text-cyan-300">
                {isInstalled ? 'PWA installed' : 'Browser mode'}
              </span>
            </div>
          </div>

          <nav className="mt-8 space-y-2">
            {navigation.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                className={({ isActive }) =>
                  cn(
                    'flex items-center gap-3 rounded-2xl px-4 py-3 text-sm font-medium transition-colors',
                    isActive
                      ? 'bg-white text-slate-950 shadow-[0_10px_30px_rgba(15,23,42,0.25)]'
                      : 'text-slate-300 hover:bg-white/8 hover:text-white'
                  )
                }
              >
                <item.icon className="h-5 w-5" />
                {item.label}
              </NavLink>
            ))}
          </nav>

          <div className="mt-auto rounded-[1.5rem] border border-amber-400/20 bg-amber-500/10 p-4 text-sm text-amber-100">
            <div className="flex items-center gap-2 font-semibold">
              <BellRing className="h-4 w-4" />
              Environment status
            </div>
            <p className="mt-2 leading-6 text-amber-50/90">
              Mock backend absent. UI is running against local contracts only, so actions validate product flow instead of persistence.
            </p>
          </div>

          <button
            type="button"
            onClick={handleLogout}
            className="mt-4 flex items-center gap-3 rounded-2xl px-4 py-3 text-sm font-medium text-slate-300 transition-colors hover:bg-rose-500/10 hover:text-rose-200"
          >
            <LogOut className="h-5 w-5" />
            Sign out
          </button>
        </aside>

        <main className="flex min-h-screen min-w-0 flex-1 flex-col">
          <header className="sticky top-0 z-40 border-b border-white/70 bg-white/80 px-4 py-4 backdrop-blur md:px-6">
            <div className="mx-auto flex max-w-7xl items-center justify-between gap-4">
              <div className="min-w-0">
                <p className="text-xs font-semibold uppercase tracking-[0.24em] text-teal-700">
                  {currentSection?.label ?? 'Workspace'}
                </p>
                <h1 className="truncate text-lg font-semibold text-slate-950 md:text-xl">
                  {currentSection?.label === 'Dashboard'
                    ? 'Fleet overview'
                    : currentSection?.label ?? 'Monitoring workspace'}
                </h1>
              </div>

              <div className="flex items-center gap-3">
                <div className="hidden rounded-full border border-slate-200 bg-slate-50 px-3 py-2 text-xs font-medium text-slate-600 md:flex md:items-center md:gap-2">
                  <Smartphone className="h-3.5 w-3.5 text-teal-700" />
                  {isInstalled ? 'Installed PWA' : 'Install available'}
                </div>
                <div className="flex h-10 w-10 items-center justify-center rounded-full bg-teal-900 text-sm font-semibold text-white">
                  {user.initials}
                </div>
              </div>
            </div>
          </header>

          <div className="mx-auto w-full max-w-7xl flex-1 px-4 py-6 md:px-6 md:py-8 pb-[calc(5.5rem+env(safe-area-inset-bottom))] lg:pb-8">
            <Outlet />
          </div>
        </main>
      </div>

      <nav className="fixed inset-x-0 bottom-0 z-50 border-t border-slate-200 bg-white/95 px-2 pb-[env(safe-area-inset-bottom)] pt-2 shadow-[0_-12px_40px_rgba(15,23,42,0.08)] backdrop-blur lg:hidden">
        <div className="grid grid-cols-4 gap-1">
          {navigation.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              className={({ isActive }) =>
                cn(
                  'flex min-h-14 flex-col items-center justify-center rounded-2xl gap-1 text-[11px] font-semibold transition-colors',
                  isActive ? 'bg-teal-900 text-white' : 'text-slate-500'
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
