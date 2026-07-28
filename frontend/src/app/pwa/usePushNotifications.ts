import { useCallback, useEffect, useState } from 'react';
import { getPushConfig, subscribePush, unsubscribePush } from '../api';

export type PushStatus =
  | 'loading'
  | 'unsupported'
  | 'disabled-on-server'
  | 'permission-denied'
  | 'subscribed'
  | 'not-subscribed';

function urlBase64ToUint8Array(base64String: string) {
  const padding = '='.repeat((4 - (base64String.length % 4)) % 4);
  const base64 = (base64String + padding).replace(/-/g, '+').replace(/_/g, '/');
  const rawData = window.atob(base64);

  return Uint8Array.from(rawData, (char) => char.charCodeAt(0));
}

async function getServiceWorkerRegistration() {
  // SW регистрируется только в production-сборке (App.tsx), поэтому в dev
  // navigator.serviceWorker.ready никогда не резолвится - проверяем без ожидания.
  if (!('serviceWorker' in navigator) || !('PushManager' in window) || !('Notification' in window)) {
    return null;
  }

  return (await navigator.serviceWorker.getRegistration()) ?? null;
}

export async function releasePushSubscription() {
  // Подписка привязана к организации, а не к устройству: строка в БД адресуется
  // по org_id, и уведомления с именами мониторов продолжают приходить сюда после
  // выхода. На общем устройстве их получал бы следующий вошедший — по каналу,
  // который вообще не проходит через авторизацию. Поэтому логаут снимает подписку
  // и в браузере, и на сервере; серверный вызов идёт ПЕРВЫМ, пока токен ещё жив.
  try {
    const registration = await getServiceWorkerRegistration();
    const subscription = registration ? await registration.pushManager.getSubscription() : null;

    if (!subscription) return;

    await unsubscribePush(subscription.endpoint).catch(() => {
      // сессия могла уже протухнуть — локальную отписку это отменять не должно:
      // без неё устройство продолжит принимать чужие уведомления
    });
    await subscription.unsubscribe();
  } catch {
    // выходу из аккаунта сбой отписки мешать не должен
  }
}

export function usePushNotifications() {
  const [status, setStatus] = useState<PushStatus>('loading');
  const [isBusy, setIsBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let ignore = false;

    async function detect(): Promise<PushStatus> {
      const registration = await getServiceWorkerRegistration();

      if (!registration) return 'unsupported';

      const config = await getPushConfig();

      if (!config.enabled) return 'disabled-on-server';
      if (Notification.permission === 'denied') return 'permission-denied';

      const subscription = await registration.pushManager.getSubscription();

      return subscription ? 'subscribed' : 'not-subscribed';
    }

    detect()
      .then((next) => {
        if (!ignore) setStatus(next);
      })
      .catch(() => {
        if (!ignore) setStatus('unsupported');
      });

    return () => {
      ignore = true;
    };
  }, []);

  const enable = useCallback(async () => {
    setIsBusy(true);
    setError(null);

    try {
      const registration = await getServiceWorkerRegistration();

      if (!registration) {
        setStatus('unsupported');
        return;
      }

      const config = await getPushConfig();

      if (!config.enabled || !config.public_key) {
        setStatus('disabled-on-server');
        return;
      }

      const permission = await Notification.requestPermission();

      if (permission !== 'granted') {
        setStatus('permission-denied');
        return;
      }

      const subscription =
        (await registration.pushManager.getSubscription()) ??
        (await registration.pushManager.subscribe({
          userVisibleOnly: true,
          applicationServerKey: urlBase64ToUint8Array(config.public_key),
        }));
      const keys = subscription.toJSON().keys ?? {};

      await subscribePush({
        endpoint: subscription.endpoint,
        keys: { p256dh: keys.p256dh ?? '', auth: keys.auth ?? '' },
      });
      setStatus('subscribed');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to enable push notifications.');
    } finally {
      setIsBusy(false);
    }
  }, []);

  const disable = useCallback(async () => {
    setIsBusy(true);
    setError(null);

    try {
      const registration = await getServiceWorkerRegistration();
      const subscription = registration ? await registration.pushManager.getSubscription() : null;

      if (subscription) {
        await subscription.unsubscribe();
        await unsubscribePush(subscription.endpoint);
      }

      setStatus('not-subscribed');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to disable push notifications.');
    } finally {
      setIsBusy(false);
    }
  }, []);

  return { status, isBusy, error, enable, disable };
}
