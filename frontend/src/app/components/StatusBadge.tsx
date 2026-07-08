import { AlertTriangle, CheckCircle2, CircleDashed, PauseCircle, XCircle } from 'lucide-react';
import { cn } from '../utils/cn';
import { getStatusLabel, type MonitorStatus } from '../api';

const toneClasses: Record<MonitorStatus, string> = {
  up: 'bg-accent text-status-up',
  down: 'bg-status-down/10 text-status-down',
  paused: 'bg-status-pending/10 text-status-pending',
  degraded: 'bg-status-degraded/15 text-status-degraded',
  pending: 'bg-status-pending/10 text-status-pending',
};

const toneIcons: Record<MonitorStatus, typeof CheckCircle2> = {
  up: CheckCircle2,
  down: XCircle,
  paused: PauseCircle,
  degraded: AlertTriangle,
  pending: CircleDashed,
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
        'inline-flex items-center gap-1.5 rounded-lg px-2.5 py-1 text-xs font-semibold',
        toneClasses[status],
        className
      )}
    >
      <Icon className="h-3.5 w-3.5" />
      {getStatusLabel(status)}
    </span>
  );
}
