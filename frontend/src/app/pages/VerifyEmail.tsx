import { useEffect, useRef, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router';
import { Activity } from 'lucide-react';
import { Button } from '../components/ui/Button';
import { Card, CardContent } from '../components/ui/Card';
import { ApiError, verifyEmail } from '../api';

type State = 'verifying' | 'success' | 'error';

export default function VerifyEmailPage() {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const token = searchParams.get('token') ?? '';
  const [state, setState] = useState<State>(token ? 'verifying' : 'error');
  const [message, setMessage] = useState(token ? '' : 'The verification link is invalid or incomplete.');
  const started = useRef(false);

  useEffect(() => {
    if (!token || started.current) return;
    started.current = true; // StrictMode монтирует дважды — токен одноразовый, шлём один раз

    verifyEmail(token)
      .then(() => setState('success'))
      .catch((error) => {
        setState('error');
        setMessage(
          error instanceof ApiError ? error.message : 'Unable to verify the email. Check backend availability.'
        );
      });
  }, [token]);

  return (
    <div className="flex min-h-screen items-center justify-center bg-background px-4 py-8 text-foreground">
      <Card className="w-full max-w-md overflow-hidden">
        <CardContent className="p-0">
          <div className="border-b border-border px-6 py-5">
            <div className="flex items-center gap-3">
              <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-primary text-primary-foreground">
                <Activity className="h-5 w-5" />
              </div>
              <div>
                <p className="text-xs font-semibold text-primary">PWA Monitor</p>
                <h1 className="text-lg font-semibold leading-6 text-foreground">Email verification</h1>
              </div>
            </div>
          </div>

          <div className="space-y-5 p-6">
            {state === 'verifying' && <p className="text-sm text-muted-foreground">Verifying your email...</p>}

            {state === 'success' && (
              <>
                <div className="rounded-lg bg-accent px-4 py-3 text-sm text-accent-foreground">
                  Your email is confirmed. You can sign in now.
                </div>
                <Button type="button" size="lg" className="w-full" onClick={() => navigate('/login')}>
                  Go to sign in
                </Button>
              </>
            )}

            {state === 'error' && (
              <>
                <div className="rounded-lg bg-destructive/10 px-4 py-3 text-sm text-destructive">{message}</div>
                <Button type="button" size="lg" className="w-full" onClick={() => navigate('/login')}>
                  Back to sign in
                </Button>
              </>
            )}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
