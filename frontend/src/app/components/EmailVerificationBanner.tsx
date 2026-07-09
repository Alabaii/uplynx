import { useState } from 'react';
import { MailWarning } from 'lucide-react';
import { resendVerification } from '../api';
import { useTexts } from '../i18n';

type ResendState = 'idle' | 'sending' | 'sent';

export function EmailVerificationBanner({ email }: { email: string }) {
  const t = useTexts({
    ru: {
      confirm: 'Подтвердите адрес электронной почты, чтобы сохранить полный доступ к аккаунту.',
      sent: 'Письмо для подтверждения отправлено.',
      sending: 'Отправка...',
      resend: 'Отправить ссылку ещё раз',
    },
    en: {
      confirm: 'Confirm your email address to keep full access to your account.',
      sent: 'Verification email sent.',
      sending: 'Sending...',
      resend: 'Resend link',
    },
  });
  const [state, setState] = useState<ResendState>('idle');

  const handleResend = async () => {
    if (!email || state !== 'idle') return;
    setState('sending');
    try {
      await resendVerification(email);
    } finally {
      // ответ всегда 204 (не раскрывает статус) — показываем «отправлено» в любом случае
      setState('sent');
    }
  };

  return (
    <div className="border-b border-status-degraded/30 bg-status-degraded/15 px-4 py-2 text-xs text-foreground md:px-6">
      <div className="mx-auto flex max-w-7xl flex-wrap items-center gap-2">
        <MailWarning className="h-3.5 w-3.5 shrink-0 text-status-degraded" />
        <span>{t.confirm}</span>
        {state === 'sent' ? (
          <span className="font-semibold text-status-degraded">{t.sent}</span>
        ) : (
          <button
            type="button"
            onClick={handleResend}
            disabled={state === 'sending'}
            className="font-semibold text-primary underline-offset-2 hover:underline disabled:opacity-60"
          >
            {state === 'sending' ? t.sending : t.resend}
          </button>
        )}
      </div>
    </div>
  );
}
