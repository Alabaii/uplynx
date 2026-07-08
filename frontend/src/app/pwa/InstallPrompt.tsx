import React, { useState } from 'react';
import { usePWA } from './usePWA';
import { Download, X, Apple } from 'lucide-react';
import { Button } from '../components/ui/Button';

export function InstallPrompt() {
  const { isInstallable, isInstalled, isIOS, promptInstall } = usePWA();
  const [dismissed, setDismissed] = useState(false);

  if (isInstalled || dismissed) return null;

  if (isInstallable) {
    return (
      <div className="fixed bottom-[calc(5rem+env(safe-area-inset-bottom))] left-4 right-4 z-50 flex items-start gap-4 rounded-lg bg-card p-4 shadow-floating animate-in slide-in-from-bottom-5 md:bottom-8 md:left-auto md:right-8 md:w-96">
        <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-accent text-primary">
          <Download className="h-5 w-5" />
        </div>
        <div className="flex-1">
          <h4 className="text-sm font-semibold leading-5 text-foreground">Install PWA workspace</h4>
          <p className="mt-1 mb-3 text-xs leading-5 text-muted-foreground">
            Install the dashboard for faster launch, cached monitor status, and future push-ready behavior.
          </p>
          <div className="flex gap-2">
            <Button size="sm" onClick={promptInstall} className="flex-1">Install</Button>
            <Button size="sm" variant="ghost" onClick={() => setDismissed(true)}>Later</Button>
          </div>
        </div>
        <button onClick={() => setDismissed(true)} className="absolute top-2 right-2 text-placeholder hover:text-muted-foreground">
          <X className="h-4 w-4" />
        </button>
      </div>
    );
  }

  if (isIOS && !isInstalled) {
    return (
      <div className="fixed bottom-[calc(5rem+env(safe-area-inset-bottom))] left-4 right-4 z-50 flex flex-col items-center gap-2 rounded-lg bg-card p-4 shadow-floating animate-in slide-in-from-bottom-5 md:bottom-8 md:left-auto md:right-8 md:w-96">
        <button onClick={() => setDismissed(true)} className="absolute top-2 right-2 text-placeholder hover:text-muted-foreground">
          <X className="h-4 w-4" />
        </button>
        <div className="mb-2 flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-secondary text-muted-foreground">
          <Apple className="h-5 w-5" />
        </div>
        <h4 className="text-center text-sm font-semibold leading-5 text-foreground">Add to Home Screen</h4>
        <p className="mb-1 text-center text-xs leading-5 text-muted-foreground">
          Install the app first. iOS web push is available only on iOS 16.4 and newer.
        </p>
        <div className="mt-2 flex w-full items-center gap-2 rounded-lg border border-border bg-secondary p-2 text-center text-xs text-muted-foreground">
          Tap <span className="inline-block rounded-sm border border-border bg-card px-1 font-serif">Share</span> then "Add to Home Screen"
        </div>
      </div>
    );
  }

  return null;
}
