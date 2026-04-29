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
      <div className="fixed bottom-[calc(5rem+env(safe-area-inset-bottom))] left-4 right-4 z-50 flex items-start gap-4 rounded-[1.5rem] border border-teal-200 bg-white/95 p-4 shadow-[0_20px_50px_rgba(15,23,42,0.16)] backdrop-blur animate-in slide-in-from-bottom-5 md:bottom-8 md:left-auto md:right-8 md:w-96">
        <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-2xl bg-teal-50 text-teal-700">
          <Download className="h-5 w-5" />
        </div>
        <div className="flex-1">
          <h4 className="font-semibold text-slate-900">Install PWA workspace</h4>
          <p className="mt-1 mb-3 text-xs leading-5 text-slate-500">
            Install the dashboard for faster launch, cached monitor status, and future push-ready behavior.
          </p>
          <div className="flex gap-2">
            <Button size="sm" onClick={promptInstall} className="flex-1">Install</Button>
            <Button size="sm" variant="ghost" onClick={() => setDismissed(true)}>Later</Button>
          </div>
        </div>
        <button onClick={() => setDismissed(true)} className="absolute top-2 right-2 text-slate-400 hover:text-slate-600">
          <X className="h-4 w-4" />
        </button>
      </div>
    );
  }

  if (isIOS && !isInstalled) {
    return (
      <div className="fixed bottom-[calc(5rem+env(safe-area-inset-bottom))] left-4 right-4 z-50 flex flex-col items-center gap-2 rounded-[1.5rem] border border-teal-200 bg-white/95 p-4 shadow-[0_20px_50px_rgba(15,23,42,0.16)] backdrop-blur animate-in slide-in-from-bottom-5 md:bottom-8 md:left-auto md:right-8 md:w-96">
        <button onClick={() => setDismissed(true)} className="absolute top-2 right-2 text-slate-400 hover:text-slate-600">
          <X className="h-4 w-4" />
        </button>
        <div className="mb-2 flex h-10 w-10 shrink-0 items-center justify-center rounded-2xl bg-slate-100 text-slate-700">
          <Apple className="h-5 w-5" />
        </div>
        <h4 className="font-semibold text-slate-900 text-center">Add to Home Screen</h4>
        <p className="mb-1 text-center text-xs leading-5 text-slate-500">
          Install the app first. iOS web push is available only on iOS 16.4 and newer.
        </p>
        <div className="mt-2 flex w-full items-center gap-2 rounded border border-slate-100 bg-slate-50 p-2 text-center text-xs text-slate-600">
          Tap <span className="inline-block px-1 border rounded bg-white font-serif">Share</span> then "Add to Home Screen"
        </div>
      </div>
    );
  }

  return null;
}
