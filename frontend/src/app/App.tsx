import { useEffect } from 'react';
import { RouterProvider } from 'react-router';
import { router } from './routes';
import { LanguageProvider } from './i18n';
import { InstallPrompt } from './pwa/InstallPrompt';

function setupPWA() {
  let manifestLink = document.querySelector('link[rel="manifest"]') as HTMLLinkElement | null;

  if (!manifestLink) {
    manifestLink = document.createElement('link');
    manifestLink.rel = 'manifest';
    manifestLink.href = '/manifest.json';
    document.head.appendChild(manifestLink);
  }

  if (import.meta.env.PROD && 'serviceWorker' in navigator) {
    // load мог пройти до монтирования React — тогда обработчик уже не вызовется
    // и воркер не зарегистрируется вовсе (ни офлайна, ни push-уведомлений)
    if (document.readyState === 'complete') {
      registerServiceWorker();
    } else {
      window.addEventListener('load', registerServiceWorker, { once: true });
    }
  }
}

function registerServiceWorker() {
  navigator.serviceWorker.register('/sw.js').catch((error) => {
    console.error('SW registration failed:', error);
  });
}

export default function App() {
  useEffect(() => {
    setupPWA();
  }, []);

  return (
    <LanguageProvider>
      <RouterProvider router={router} />
      <InstallPrompt />
    </LanguageProvider>
  );
}
