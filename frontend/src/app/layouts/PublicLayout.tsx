import { Link, Outlet } from 'react-router';
import { Activity } from 'lucide-react';
import { LanguageSwitcher, useTexts } from '../i18n';

export function PublicLayout() {
  const t = useTexts({
    ru: {
      pricing: 'Тарифы',
      contacts: 'Контакты',
      signIn: 'Войти',
      signUp: 'Регистрация',
      legal: 'Документы',
      offer: 'Публичная оферта',
      privacy: 'Политика персональных данных',
      payments: 'Оплата и возврат',
      rights: 'Все права защищены.',
    },
    en: {
      pricing: 'Pricing',
      contacts: 'Contacts',
      signIn: 'Sign in',
      signUp: 'Sign up',
      legal: 'Legal',
      offer: 'Public offer',
      privacy: 'Privacy policy',
      payments: 'Payments and refunds',
      rights: 'All rights reserved.',
    },
  });

  return (
    <div className="flex min-h-screen flex-col bg-background text-foreground">
      <header className="border-b border-border bg-card">
        <div className="mx-auto flex h-16 max-w-6xl items-center justify-between gap-4 px-4">
          <Link to="/welcome" className="flex items-center gap-2.5">
            <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-accent text-primary">
              <Activity className="h-5 w-5" />
            </span>
            <span className="text-lg font-semibold">Uplynx</span>
          </Link>
          <nav className="flex items-center gap-1 sm:gap-3">
            <Link to="/pricing" className="rounded-lg px-2 py-1.5 text-sm font-medium hover:text-primary sm:px-3">
              {t.pricing}
            </Link>
            <Link
              to="/contacts"
              className="hidden rounded-lg px-3 py-1.5 text-sm font-medium hover:text-primary sm:block"
            >
              {t.contacts}
            </Link>
            <LanguageSwitcher />
            <Link to="/login" className="rounded-lg px-2 py-1.5 text-sm font-medium hover:text-primary sm:px-3">
              {t.signIn}
            </Link>
            <Link
              to="/register"
              className="rounded-lg bg-primary px-3 py-1.5 text-sm font-medium text-primary-foreground hover:bg-primary-hover"
            >
              {t.signUp}
            </Link>
          </nav>
        </div>
      </header>

      <main className="flex-1">
        <Outlet />
      </main>

      <footer className="border-t border-border bg-card">
        <div className="mx-auto grid max-w-6xl gap-8 px-4 py-10 sm:grid-cols-3">
          <div>
            <p className="flex items-center gap-2 text-sm font-semibold">
              <Activity className="h-4 w-4 text-primary" />
              Uplynx
            </p>
            <p className="mt-2 text-xs text-muted-foreground">
              © {new Date().getFullYear()} Uplynx. {t.rights}
            </p>
          </div>
          <div className="space-y-1.5 text-sm">
            <p className="text-xs font-semibold uppercase tracking-wide text-placeholder">{t.legal}</p>
            <p><Link to="/legal/offer" className="hover:text-primary">{t.offer}</Link></p>
            <p><Link to="/legal/privacy" className="hover:text-primary">{t.privacy}</Link></p>
            <p><Link to="/legal/payments" className="hover:text-primary">{t.payments}</Link></p>
          </div>
          <div className="space-y-1.5 text-sm">
            <p className="text-xs font-semibold uppercase tracking-wide text-placeholder">{t.contacts}</p>
            <p><Link to="/contacts" className="hover:text-primary">{t.contacts}</Link></p>
            <p><Link to="/pricing" className="hover:text-primary">{t.pricing}</Link></p>
          </div>
        </div>
      </footer>
    </div>
  );
}
