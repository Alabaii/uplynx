import { useEffect, useState } from 'react';
import { Link } from 'react-router';
import { Check } from 'lucide-react';
import { getPublicPlans, type Plan } from '../api';
import { plural, useTexts } from '../i18n';

function formatRub(kopeks: number): string {
  return `${Math.round(kopeks / 100).toLocaleString('ru-RU')} ₽`;
}

function formatInterval(seconds: number, lang: 'ru' | 'en'): string {
  if (seconds < 60) return lang === 'ru' ? `${seconds} сек` : `${seconds}s`;
  const minutes = Math.round(seconds / 60);
  return lang === 'ru' ? `${minutes} мин` : `${minutes} min`;
}

export default function Pricing() {
  const [plans, setPlans] = useState<Plan[]>([]);
  const [error, setError] = useState(false);
  const t = useTexts({
    ru: {
      lang: 'ru' as const,
      title: 'Тарифы',
      subtitle:
        'Цены в рублях, оплата картой или через СБП. Тариф можно сменить в любой момент — ' +
        'при переходе на меньший лишние мониторы ставятся на паузу, данные не удаляются.',
      free: 'Бесплатно',
      perMonth: '/мес',
      annual: (price: string) => `≈ ${price}/мес при оплате за год`,
      monitors: (n: number) => `${n} ${plural(n, ['монитор', 'монитора', 'мониторов'])}`,
      interval: (v: string) => `проверки от ${v}`,
      browser: (n: number) =>
        n > 0 ? `${n} browser-${plural(n, ['проверка', 'проверки', 'проверок'])}` : 'без browser-проверок',
      members: (n: number | null) =>
        n === null ? 'участники без ограничений' : `${n} ${plural(n, ['участник', 'участника', 'участников'])}`,
      retention: (d: number) => (d >= 365 ? 'история за год' : `история за ${d} ${plural(d, ['день', 'дня', 'дней'])}`),
      alerts: 'Telegram, push и email-алерты',
      statusPage: 'публичная статус-страница',
      ssl: 'SSL-мониторинг',
      cta: 'Начать',
      note:
        'Оплата подписки — через ЮKassa (банковские карты, СБП). Чек приходит на email. ' +
        'Подробнее — на странице «Оплата и возврат».',
      loadError: 'Не удалось загрузить тарифы. Обновите страницу.',
      popular: 'популярный',
    },
    en: {
      lang: 'en' as const,
      title: 'Pricing',
      subtitle:
        'Prices in rubles, payable by card or SBP. Change your plan anytime — ' +
        'on downgrade extra monitors are paused, nothing is deleted.',
      free: 'Free',
      perMonth: '/mo',
      annual: (price: string) => `≈ ${price}/mo billed annually`,
      monitors: (n: number) => `${n} monitors`,
      interval: (v: string) => `checks from ${v}`,
      browser: (n: number) => (n > 0 ? `${n} browser checks` : 'no browser checks'),
      members: (n: number | null) => (n === null ? 'unlimited members' : `${n} team members`),
      retention: (d: number) => (d >= 365 ? '1 year history' : `${d} days history`),
      alerts: 'Telegram, push and email alerts',
      statusPage: 'public status page',
      ssl: 'SSL monitoring',
      cta: 'Get started',
      note:
        'Subscriptions are billed via YooKassa (bank cards, SBP). A receipt is emailed to you. ' +
        'See “Payments and refunds” for details.',
      loadError: 'Unable to load pricing. Refresh the page.',
      popular: 'popular',
    },
  });

  useEffect(() => {
    let ignore = false;
    getPublicPlans()
      .then((list) => {
        if (!ignore) {
          setPlans(list);
          setError(false);
        }
      })
      .catch(() => {
        if (!ignore) setError(true);
      });
    return () => {
      ignore = true;
    };
  }, []);

  return (
    <div className="mx-auto max-w-6xl px-4 py-14">
      <h1 className="text-center text-3xl font-semibold">{t.title}</h1>
      <p className="mx-auto mt-4 max-w-2xl text-center text-sm leading-6 text-muted-foreground">{t.subtitle}</p>

      {error && (
        <p className="mt-10 text-center text-sm text-destructive">{t.loadError}</p>
      )}

      <div className="mt-12 grid gap-5 lg:grid-cols-3">
        {plans.map((plan) => {
          const isPopular = plan.slug === 'pro';
          const annualKopeks = plan.price_monthly_kopeks * (1 - plan.annual_discount_pct / 100);
          const perks = [
            t.monitors(plan.max_monitors),
            t.interval(formatInterval(plan.min_interval_seconds, t.lang)),
            t.browser(plan.max_browser_monitors),
            t.members(plan.max_members),
            t.retention(plan.retention_days),
            t.alerts,
            t.statusPage,
            t.ssl,
          ];
          return (
            <div
              key={plan.slug}
              className={`relative rounded-lg bg-card p-7 shadow-card ${isPopular ? 'ring-2 ring-primary' : ''}`}
            >
              {isPopular && (
                <span className="absolute -top-3 left-1/2 -translate-x-1/2 rounded-lg bg-primary px-3 py-0.5 text-xs font-semibold text-primary-foreground">
                  {t.popular}
                </span>
              )}
              <p className="text-sm font-semibold text-primary">{plan.name}</p>
              <p className="mt-3 text-4xl font-semibold">
                {plan.price_monthly_kopeks === 0 ? t.free : formatRub(plan.price_monthly_kopeks)}
                {plan.price_monthly_kopeks > 0 && (
                  <span className="text-base font-normal text-muted-foreground">{t.perMonth}</span>
                )}
              </p>
              {plan.price_monthly_kopeks > 0 && plan.annual_discount_pct > 0 && (
                <p className="mt-1 text-xs text-muted-foreground">{t.annual(formatRub(annualKopeks))}</p>
              )}
              <ul className="mt-6 space-y-2.5">
                {perks.map((perk) => (
                  <li key={perk} className="flex items-start gap-2 text-sm">
                    <Check className="mt-0.5 h-4 w-4 shrink-0 text-primary" />
                    {perk}
                  </li>
                ))}
              </ul>
              <Link
                to="/register"
                className={`mt-7 block rounded-lg px-4 py-2.5 text-center text-sm font-semibold ${
                  isPopular
                    ? 'bg-primary text-primary-foreground hover:bg-primary-hover'
                    : 'bg-secondary text-primary hover:bg-accent'
                }`}
              >
                {t.cta}
              </Link>
            </div>
          );
        })}
      </div>

      <p className="mx-auto mt-10 max-w-2xl text-center text-xs leading-5 text-placeholder">{t.note}</p>
    </div>
  );
}
