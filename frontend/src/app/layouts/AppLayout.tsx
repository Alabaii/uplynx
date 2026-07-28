import { useEffect, useState } from 'react';
import { NavLink, Outlet, useLocation, useNavigate } from 'react-router';
import { Activity, LogOut, Search, ShieldCheck, Smartphone } from 'lucide-react';
import { clearSession, getSessionEmail } from '../auth';
import { CommandPalette } from '../components/CommandPalette';
import { EmailVerificationBanner } from '../components/EmailVerificationBanner';
import { OfflineBanner } from '../components/OfflineBanner';
import { getMe, logout } from '../api';
import { LanguageSwitcher, useLang, useTexts } from '../i18n';
import { useDeploymentMode } from '../meta-context';
import { OrgSwitcher } from './OrgSwitcher';
import { navLabel, navigation } from './navigation';
import { usePWA } from '../pwa/usePWA';
import { releasePushSubscription } from '../pwa/usePushNotifications';
import { cn } from '../utils/cn';

// нижняя навигация на мобиле — ровно 5 пунктов в grid-cols-5; Incidents и Maintenance доступны
// на десктопе, поэтому здесь они опущены, чтобы не ломать сетку лишними пунктами
const mobileNavigation = navigation.filter((item) => item.to !== '/incidents' && item.to !== '/maintenance');

export function AppLayout() {
  const navigate = useNavigate();
  const location = useLocation();
  const { isInstalled } = usePWA();
  const [isOffline, setIsOffline] = useState(() => typeof navigator !== 'undefined' && !navigator.onLine);
  const [email, setEmail] = useState(() => getSessionEmail() ?? '');
  const [orgName, setOrgName] = useState('My team');
  const [orgId, setOrgId] = useState<number | null>(null);
  const [paletteOpen, setPaletteOpen] = useState(false);
  // default true — не мигаем баннером до ответа /me
  const [emailVerified, setEmailVerified] = useState(true);
  const [isSuperuser, setIsSuperuser] = useState(false);
  const isEnterprise = useDeploymentMode() === 'enterprise';
  const { lang } = useLang();
  const t = useTexts({
    ru: {
      tagline: 'Мониторинг сервисов',
      activeWorkspace: 'Текущий воркспейс',
      signedIn: 'Вы вошли',
      pwaInstalled: 'PWA установлено',
      browserMode: 'В браузере',
      signOut: 'Выйти',
      fleetOverview: 'Обзор мониторов',
      workspaceFallback: 'Рабочая область',
      search: 'Поиск',
      installedPwa: 'PWA установлено',
      installAvailable: 'Можно установить',
      operator: 'Оператор',
      admin: 'Админка',
    },
    en: {
      tagline: 'Monitoring ops',
      activeWorkspace: 'Active workspace',
      signedIn: 'Signed in',
      pwaInstalled: 'PWA installed',
      browserMode: 'Browser mode',
      signOut: 'Sign out',
      fleetOverview: 'Fleet overview',
      workspaceFallback: 'Monitoring workspace',
      search: 'Search',
      installedPwa: 'Installed PWA',
      installAvailable: 'Install available',
      operator: 'Operator',
      admin: 'Admin',
    },
  });

  useEffect(() => {
    let ignore = false;

    getMe()
      .then((user) => {
        if (!ignore) {
          setEmail(user.email);
          setOrgName(user.organization?.name ?? 'My team');
          setOrgId(user.organization?.id ?? null);
          setEmailVerified(user.email_verified ?? true);
          setIsSuperuser(user.is_superuser ?? false);
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

  const handleLogout = async () => {
    // push-подписка принадлежит организации, а не устройству: без снятия следующий
    // вошедший на этом устройстве продолжал бы получать уведомления предыдущего
    // воркспейса. Снимаем ДО очистки сессии — серверной отписке нужен живой токен
    await releasePushSubscription();
    // отзываем refresh-сессию на сервере; сбой не мешает локальному выходу
    logout().catch(() => {});
    // токены снимаются синхронно, но офлайн-кэш чистится асинхронно — дожидаемся
    // до навигации, чтобы данные организации не остались на устройстве
    await clearSession();
    navigate('/login');
  };

  // /admin виден только суперадмину и только в десктопном сайдбаре:
  // мобильная нижняя навигация фиксирована на 5 пунктах (grid-cols-5)
  const adminItem = { to: '/admin', label: 'Admin', labelRu: t.admin, icon: ShieldCheck };
  const sidebarNavigation = isSuperuser ? [...navigation, adminItem] : navigation;

  const currentSection = sidebarNavigation.find((item) =>
    item.to === '/' ? location.pathname === '/' : location.pathname.startsWith(item.to)
  );

  return (
    <div className="min-h-screen bg-background">
      <CommandPalette open={paletteOpen} onOpenChange={setPaletteOpen} />
      {isOffline && <OfflineBanner />}
      {!emailVerified && <EmailVerificationBanner email={email} />}

      <div className="mx-auto flex min-h-screen max-w-[1600px]">
        <aside className="sticky top-0 hidden h-screen w-72 shrink-0 bg-card px-4 py-6 shadow-card lg:flex lg:flex-col">
          <div className="flex items-center gap-3 px-2">
            <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-accent text-primary">
              <Activity className="h-6 w-6" />
            </div>
            <div>
              <p className="text-lg font-semibold text-foreground">Uplynx Console</p>
              <p className="text-xs text-placeholder">{t.tagline}</p>
            </div>
          </div>

          <div className="mt-6 rounded-lg bg-secondary p-4">
            {isEnterprise ? (
              <OrgSwitcher orgName={orgName} currentOrgId={orgId} />
            ) : (
              <>
                <p className="text-xs text-placeholder">{t.activeWorkspace}</p>
                <p className="mt-1 text-sm font-semibold text-foreground">{orgName}</p>
              </>
            )}
            <p className="mt-0.5 truncate text-xs text-muted-foreground">{email || t.signedIn}</p>
            <div className="mt-3 flex flex-wrap gap-2">
              <span className="rounded-lg bg-accent px-2.5 py-1 text-xs font-semibold text-primary">
                {isInstalled ? t.pwaInstalled : t.browserMode}
              </span>
            </div>
          </div>

          <nav className="mt-6 space-y-1">
            {sidebarNavigation.map((item) => (
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
                {navLabel(item, lang)}
              </NavLink>
            ))}
          </nav>

          <button
            type="button"
            onClick={handleLogout}
            className="mt-auto flex items-center gap-3 rounded-lg px-3 py-2.5 text-sm font-medium text-muted-foreground transition-colors hover:text-destructive"
          >
            <LogOut className="h-5 w-5" />
            {t.signOut}
          </button>
        </aside>

        <main className="flex min-h-screen min-w-0 flex-1 flex-col">
          <header className="sticky top-0 z-40 h-[60px] border-b border-border bg-background px-4 md:px-6">
            <div className="mx-auto flex h-full max-w-7xl items-center justify-between gap-4">
              <div className="min-w-0">
                <h1 className="truncate text-lg font-semibold leading-6 text-foreground">
                  {currentSection?.label === 'Dashboard'
                    ? t.fleetOverview
                    : currentSection
                      ? navLabel(currentSection, lang)
                      : t.workspaceFallback}
                </h1>
              </div>

              <div className="flex items-center gap-3">
                <LanguageSwitcher />
                <button
                  type="button"
                  onClick={() => setPaletteOpen(true)}
                  className="hidden items-center gap-2 rounded-lg bg-card px-3 py-1.5 text-xs font-medium text-muted-foreground shadow-card transition-colors hover:text-primary md:flex"
                >
                  <Search className="h-3.5 w-3.5" />
                  {t.search}
                  <kbd className="rounded bg-secondary px-1.5 py-0.5 text-[10px] font-semibold text-placeholder">
                    Ctrl K
                  </kbd>
                </button>
                <div className="hidden rounded-lg bg-card px-3 py-1.5 text-xs font-medium text-muted-foreground shadow-card md:flex md:items-center md:gap-2">
                  <Smartphone className="h-3.5 w-3.5 text-primary" />
                  {isInstalled ? t.installedPwa : t.installAvailable}
                </div>
                <div className="flex items-center gap-3">
                  <div className="flex h-8 w-8 items-center justify-center rounded-full bg-border text-sm font-semibold text-muted-foreground">
                    {(email[0] ?? '?').toUpperCase()}
                  </div>
                  <div className="hidden min-w-0 md:block">
                    <p className="max-w-[14rem] truncate text-sm leading-5 text-foreground">{email || t.operator}</p>
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
        <div className="grid grid-cols-5 gap-1">
          {mobileNavigation.map((item) => (
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
              <span>{navLabel(item, lang)}</span>
            </NavLink>
          ))}
        </div>
      </nav>
    </div>
  );
}
