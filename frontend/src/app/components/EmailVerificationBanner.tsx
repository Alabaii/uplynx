import { useState } from 'react';
import { MailWarning } from 'lucide-react';
import { resendVerification } from '../api';

type ResendState = 'idle' | 'sending' | 'sent';

export function EmailVerificationBanner({ email }: { email: string }) {
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
        <span>Confirm your email address to keep full access to your account.</span>
        {state === 'sent' ? (
          <span className="font-semibold text-status-degraded">Verification email sent.</span>
        ) : (
          <button
            type="button"
            onClick={handleResend}
            disabled={state === 'sending'}
            className="font-semibold text-primary underline-offset-2 hover:underline disabled:opacity-60"
          >
            {state === 'sending' ? 'Sending...' : 'Resend link'}
          </button>
        )}
      </div>
    </div>
  );
}
