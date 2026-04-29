import { AlertTriangle, CheckCircle2, PauseCircle, XCircle } from 'lucide-react';
import { cn } from '../utils/cn';
import { getStatusLabel, type MonitorStatus } from '../data/mockMonitoring';

const toneClasses: Record<MonitorStatus, string> = {
  up: 'border-emerald-200 bg-emerald-50 text-emerald-700',
  down: 'border-rose-200 bg-rose-50 text-rose-700',
  paused: 'border-slate-200 bg-slate-100 text-slate-700',
  degraded: 'border-amber-200 bg-amber-50 text-amber-700',
};

const toneIcons: Record<MonitorStatus, typeof CheckCircle2> = {
  up: CheckCircle2,
  down: XCircle,
  paused: PauseCircle,
  degraded: AlertTriangle,
};

export function StatusBadge({
  status,
  className,
}: {
  status: MonitorStatus;
  className?: string;
}) {
  const Icon = toneIcons[status];

  return (
    <span
      className={cn(
        'inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs font-semibold',
        toneClasses[status],
        className
      )}
    >
      <Icon className="h-3.5 w-3.5" />
      {getStatusLabel(status)}
    </span>
  );
}
