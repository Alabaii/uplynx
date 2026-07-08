import { CloudOff } from 'lucide-react';

export function OfflineBanner() {
  return (
    <div className="border-b border-status-degraded/30 bg-status-degraded/15 px-4 py-2 text-xs text-foreground md:px-6">
      <div className="mx-auto flex max-w-7xl items-center gap-2">
        <CloudOff className="h-3.5 w-3.5 shrink-0 text-status-degraded" />
        Offline mode: showing cached data. Alerts and config sync will resume once you are back online.
      </div>
    </div>
  );
}
