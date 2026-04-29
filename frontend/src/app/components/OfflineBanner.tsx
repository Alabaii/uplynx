import { CloudOff } from 'lucide-react';

export function OfflineBanner() {
  return (
    <div className="border-b border-amber-200 bg-amber-50 px-4 py-2 text-xs text-amber-900 md:px-6">
      <div className="mx-auto flex max-w-7xl items-center gap-2">
        <CloudOff className="h-3.5 w-3.5 shrink-0" />
        Offline mode: showing cached mock data. Push alerts and config sync will resume once you are back online.
      </div>
    </div>
  );
}
