import { CloudOff } from 'lucide-react';
import { useTexts } from '../i18n';

export function OfflineBanner() {
  const t = useTexts({
    ru: {
      message:
        'Офлайн-режим: показаны кэшированные данные. Алерты и синхронизация конфигурации возобновятся, когда появится сеть.',
    },
    en: {
      message:
        'Offline mode: showing cached data. Alerts and config sync will resume once you are back online.',
    },
  });
  return (
    <div className="border-b border-status-degraded/30 bg-status-degraded/15 px-4 py-2 text-xs text-foreground md:px-6">
      <div className="mx-auto flex max-w-7xl items-center gap-2">
        <CloudOff className="h-3.5 w-3.5 shrink-0 text-status-degraded" />
        {t.message}
      </div>
    </div>
  );
}
