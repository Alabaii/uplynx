import { useEffect, useState } from 'react';
import { Link } from 'react-router';
import {
  Activity,
  BellRing,
  FileCode2,
  Globe,
  MonitorSmartphone,
  ShieldCheck,
  Siren,
  Users,
} from 'lucide-react';
import { getPublicPlans, type Plan } from '../api';
import { useTexts } from '../i18n';
import { useMeta } from '../meta-context';

function formatRub(kopeks: number): string {
  return `${Math.round(kopeks / 100).toLocaleString('ru-RU')} ₽`;
}

export default function Landing() {
  const [plans, setPlans] = useState<Plan[]>([]);
  const t = useTexts({
    ru: {
      heroTitle: 'Мониторинг сайтов и сервисов с алертами за минуту',
      heroText:
        'Uplynx проверяет ваши сайты, API и браузерные сценарии, открывает инциденты ' +
        'при сбоях и мгновенно сообщает в Telegram, push или на почту. ' +
        'Публичная статус-страница покажет клиентам, что у вас всё под контролем.',
      ctaStart: 'Начать бесплатно',
      ctaPricing: 'Смотреть тарифы',
      featuresTitle: 'Всё, что нужно для спокойного сна',
      // подменяет первый пункт, когда браузерные сценарии выключены на инсталляции:
      // обещать на лендинге то, чего продукт сейчас не даёт, нельзя
      featureChecksHttpOnly: {
        title: 'HTTP-проверки',
        text: 'Статус ответа, текст в теле и время отклика — с анти-флаппингом и настраиваемым интервалом.',
      },
      features: [
        {
          title: 'HTTP- и browser-проверки',
          text: 'От простого пинга до сценария «открой страницу, залогинься, проверь текст» на реальном Chromium.',
        },
        {
          title: 'Алерты без спама',
          text: 'Telegram, web-push и email. Анти-флаппинг не разбудит из-за одного мигнувшего запроса.',
        },
        {
          title: 'Инциденты и история',
          text: 'Каждый сбой — инцидент с длительностью и причиной. История проверок хранится до года.',
        },
        {
          title: 'Публичная статус-страница',
          text: 'Страница состояния сервисов для ваших клиентов — включается одним переключателем.',
        },
        {
          title: 'Конфигурация как код',
          text: 'Мониторы редактируются и в интерфейсе, и как YAML — с версиями и откатом.',
        },
        {
          title: 'Команда и роли',
          text: 'Общий воркспейс, роли от наблюдателя до владельца, аудит всех действий.',
        },
      ],
      sslNote: 'Плюс SSL-мониторинг: предупредим за 30, 14, 7 и 1 день до истечения сертификата.',
      plansTitle: 'Простые тарифы в рублях',
      perMonth: '/мес',
      free: 'бесплатно',
      monitorsLabel: 'мониторов',
      plansCta: 'Подробнее о тарифах',
      bottomTitle: 'Подключите первый монитор за минуту',
      bottomText: 'Бесплатный тариф без карты. Установите как PWA на телефон — алерты всегда с вами.',
    },
    en: {
      heroTitle: 'Website and service monitoring with alerts in a minute',
      heroText:
        'Uplynx checks your websites, APIs and browser flows, opens incidents on failures ' +
        'and instantly notifies you via Telegram, push or email. ' +
        'A public status page shows your customers everything is under control.',
      ctaStart: 'Start for free',
      ctaPricing: 'See pricing',
      featuresTitle: 'Everything you need to sleep well',
      featureChecksHttpOnly: {
        title: 'HTTP checks',
        text: 'Response status, body text and response time — with anti-flapping and a configurable interval.',
      },
      features: [
        {
          title: 'HTTP and browser checks',
          text: 'From a simple ping to “open page, log in, assert text” scenarios on real Chromium.',
        },
        {
          title: 'Alerts without noise',
          text: 'Telegram, web push and email. Anti-flapping won’t wake you up over a single blip.',
        },
        {
          title: 'Incidents and history',
          text: 'Every outage becomes an incident with duration and cause. Check history is kept for up to a year.',
        },
        {
          title: 'Public status page',
          text: 'A status page for your customers — enabled with a single toggle.',
        },
        {
          title: 'Configuration as code',
          text: 'Monitors are editable both in the UI and as YAML — versioned, with rollback.',
        },
        {
          title: 'Team and roles',
          text: 'Shared workspace, roles from viewer to owner, full audit log.',
        },
      ],
      sslNote: 'Plus SSL monitoring: we warn you 30, 14, 7 and 1 day before a certificate expires.',
      plansTitle: 'Simple pricing in rubles',
      perMonth: '/mo',
      free: 'free',
      monitorsLabel: 'monitors',
      plansCta: 'See full pricing',
      bottomTitle: 'Add your first monitor in a minute',
      bottomText: 'Free plan, no card required. Install as a PWA — alerts always in your pocket.',
    },
  });

  const featureIcons = [Globe, BellRing, Siren, ShieldCheck, FileCode2, Users];
  // сценарии могут быть выключены на инсталляции — подменяем первый пункт, а не
  // убираем его: иконки сопоставлены пунктам по индексу
  const browserEnabled = useMeta()?.browser_monitors_enabled ?? false;
  const features = browserEnabled ? t.features : [t.featureChecksHttpOnly, ...t.features.slice(1)];

  useEffect(() => {
    let ignore = false;
    getPublicPlans()
      .then((list) => {
        if (!ignore) setPlans(list);
      })
      .catch(() => {
        // блок тарифов на лендинге вторичен — при недоступном API просто не показываем
      });
    return () => {
      ignore = true;
    };
  }, []);

  return (
    <div>
      <section className="mx-auto max-w-6xl px-4 pb-16 pt-14 text-center sm:pt-20">
        <div className="mx-auto mb-6 flex h-14 w-14 items-center justify-center rounded-2xl bg-accent text-primary">
          <Activity className="h-7 w-7" />
        </div>
        <h1 className="mx-auto max-w-3xl text-3xl font-semibold leading-tight sm:text-4xl">{t.heroTitle}</h1>
        <p className="mx-auto mt-5 max-w-2xl text-base leading-6 text-muted-foreground">{t.heroText}</p>
        <div className="mt-8 flex flex-wrap items-center justify-center gap-3">
          <Link
            to="/register"
            className="rounded-lg bg-primary px-5 py-2.5 text-sm font-semibold text-primary-foreground hover:bg-primary-hover"
          >
            {t.ctaStart}
          </Link>
          <Link
            to="/pricing"
            className="rounded-lg bg-card px-5 py-2.5 text-sm font-semibold text-primary shadow-card hover:bg-accent"
          >
            {t.ctaPricing}
          </Link>
        </div>
      </section>

      <section className="bg-card py-16">
        <div className="mx-auto max-w-6xl px-4">
          <h2 className="text-center text-2xl font-semibold">{t.featuresTitle}</h2>
          <div className="mt-10 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {features.map((feature, index) => {
              const Icon = featureIcons[index] ?? Globe;
              return (
                <div key={feature.title} className="rounded-lg bg-background p-6">
                  <span className="flex h-10 w-10 items-center justify-center rounded-lg bg-accent text-primary">
                    <Icon className="h-5 w-5" />
                  </span>
                  <h3 className="mt-4 text-base font-semibold">{feature.title}</h3>
                  <p className="mt-2 text-sm leading-5 text-muted-foreground">{feature.text}</p>
                </div>
              );
            })}
          </div>
          <p className="mt-8 text-center text-sm text-muted-foreground">{t.sslNote}</p>
        </div>
      </section>

      {plans.length > 0 && (
        <section className="mx-auto max-w-6xl px-4 py-16">
          <h2 className="text-center text-2xl font-semibold">{t.plansTitle}</h2>
          <div className="mt-10 grid gap-4 sm:grid-cols-3">
            {plans.map((plan) => (
              <div key={plan.slug} className="rounded-lg bg-card p-6 text-center shadow-card">
                <p className="text-sm font-semibold text-primary">{plan.name}</p>
                <p className="mt-2 text-3xl font-semibold">
                  {plan.price_monthly_kopeks === 0 ? t.free : formatRub(plan.price_monthly_kopeks)}
                  {plan.price_monthly_kopeks > 0 && (
                    <span className="text-sm font-normal text-muted-foreground">{t.perMonth}</span>
                  )}
                </p>
                <p className="mt-1 text-sm text-muted-foreground">
                  {plan.max_monitors} {t.monitorsLabel}
                </p>
              </div>
            ))}
          </div>
          <p className="mt-6 text-center">
            <Link to="/pricing" className="text-sm font-semibold text-primary hover:underline">
              {t.plansCta} →
            </Link>
          </p>
        </section>
      )}

      <section className="bg-card py-16 text-center">
        <div className="mx-auto max-w-2xl px-4">
          <MonitorSmartphone className="mx-auto h-10 w-10 text-primary" />
          <h2 className="mt-4 text-2xl font-semibold">{t.bottomTitle}</h2>
          <p className="mt-3 text-sm text-muted-foreground">{t.bottomText}</p>
          <Link
            to="/register"
            className="mt-6 inline-block rounded-lg bg-primary px-5 py-2.5 text-sm font-semibold text-primary-foreground hover:bg-primary-hover"
          >
            {t.ctaStart}
          </Link>
        </div>
      </section>
    </div>
  );
}
