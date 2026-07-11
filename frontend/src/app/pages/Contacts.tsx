import { Mail, MessageCircleQuestion, UserRound } from 'lucide-react';
import { useTexts } from '../i18n';

// Реквизиты самозанятого — требование модерации платёжного провайдера.
// Плейсхолдеры [.] заполняет владелец до публикации (см. DEPLOY.md).

function Placeholder({ children }: { children: string }) {
  return <mark className="rounded bg-status-degraded/30 px-1 font-semibold">[{children}]</mark>;
}

export default function Contacts() {
  const t = useTexts({
    ru: {
      title: 'Контакты',
      subtitle: 'Вопросы по работе сервиса, оплате и возвратам — пишите, отвечаем в течение одного рабочего дня.',
      emailTitle: 'Email',
      sellerTitle: 'Исполнитель',
      seller: 'самозанятый (плательщик налога на профессиональный доход)',
      inn: 'ИНН',
      supportTitle: 'Поддержка',
      supportText: 'Опишите проблему и приложите название монитора или организации — так мы разберёмся быстрее.',
    },
    en: {
      title: 'Contacts',
      subtitle: 'Questions about the service, billing or refunds — write to us, we reply within one business day.',
      emailTitle: 'Email',
      sellerTitle: 'Service provider',
      seller: 'self-employed individual (Russian NPD tax regime)',
      inn: 'Taxpayer ID (INN)',
      supportTitle: 'Support',
      supportText: 'Describe the issue and mention your monitor or organization name — it helps us respond faster.',
    },
  });

  return (
    <div className="mx-auto max-w-3xl px-4 py-14">
      <h1 className="text-3xl font-semibold">{t.title}</h1>
      <p className="mt-4 text-sm leading-6 text-muted-foreground">{t.subtitle}</p>

      <div className="mt-10 space-y-4">
        <div className="flex items-start gap-4 rounded-lg bg-card p-6 shadow-card">
          <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-accent text-primary">
            <Mail className="h-5 w-5" />
          </span>
          <div>
            <p className="text-sm font-semibold">{t.emailTitle}</p>
            <p className="mt-1 text-sm text-muted-foreground">
              <Placeholder>email для связи</Placeholder>
            </p>
          </div>
        </div>

        <div className="flex items-start gap-4 rounded-lg bg-card p-6 shadow-card">
          <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-accent text-primary">
            <UserRound className="h-5 w-5" />
          </span>
          <div>
            <p className="text-sm font-semibold">{t.sellerTitle}</p>
            <p className="mt-1 text-sm text-muted-foreground">
              <Placeholder>Фамилия Имя Отчество</Placeholder>, {t.seller}, {t.inn}{' '}
              <Placeholder>ИНН</Placeholder>
            </p>
          </div>
        </div>

        <div className="flex items-start gap-4 rounded-lg bg-card p-6 shadow-card">
          <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-accent text-primary">
            <MessageCircleQuestion className="h-5 w-5" />
          </span>
          <div>
            <p className="text-sm font-semibold">{t.supportTitle}</p>
            <p className="mt-1 text-sm text-muted-foreground">{t.supportText}</p>
          </div>
        </div>
      </div>
    </div>
  );
}
