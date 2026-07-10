import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router';
import { Globe, MonitorSmartphone } from 'lucide-react';
import {
  CommandDialog,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
  CommandSeparator,
} from './ui/command';
import { listMonitors, type Monitor } from '../api';
import { navigation, navLabel } from '../layouts/navigation';
import { useLang, useTexts } from '../i18n';
import { cn } from '../utils/cn';

const statusDotClasses: Record<string, string> = {
  up: 'bg-status-up',
  down: 'bg-status-down',
  degraded: 'bg-status-degraded',
  paused: 'bg-status-pending',
  pending: 'bg-status-pending',
};

export function CommandPalette({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const { lang } = useLang();
  const t = useTexts({
    ru: {
      title: 'Палитра команд',
      description: 'Поиск мониторов и страниц',
      placeholder: 'Поиск по мониторам и страницам...',
      noResults: 'Ничего не найдено.',
      monitors: 'Мониторы',
      pages: 'Страницы',
    },
    en: {
      title: 'Command palette',
      description: 'Search monitors and pages',
      placeholder: 'Search monitors and pages...',
      noResults: 'No results found.',
      monitors: 'Monitors',
      pages: 'Pages',
    },
  });
  const navigate = useNavigate();
  const [monitors, setMonitors] = useState<Monitor[] | null>(null);

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key.toLowerCase() === 'k' && (event.ctrlKey || event.metaKey)) {
        event.preventDefault();
        onOpenChange(!open);
      }
    };

    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [open, onOpenChange]);

  useEffect(() => {
    if (!open || monitors !== null) return;

    let ignore = false;

    listMonitors()
      .then((items) => {
        if (!ignore) setMonitors(items);
      })
      .catch(() => {
        if (!ignore) setMonitors([]);
      });

    return () => {
      ignore = true;
    };
  }, [open, monitors]);

  useEffect(() => {
    // при каждом открытии список запрашивается заново — статусы мониторов живые
    if (!open) setMonitors(null);
  }, [open]);

  const go = (to: string) => {
    onOpenChange(false);
    navigate(to);
  };

  return (
    <CommandDialog open={open} onOpenChange={onOpenChange} title={t.title} description={t.description}>
      <CommandInput placeholder={t.placeholder} />
      <CommandList>
        <CommandEmpty>{t.noResults}</CommandEmpty>
        {monitors !== null && monitors.length > 0 && (
          <CommandGroup heading={t.monitors}>
            {monitors.map((monitor) => (
              <CommandItem
                key={monitor.id}
                value={`${monitor.name} ${monitor.id}`}
                onSelect={() => go(`/monitors/${encodeURIComponent(monitor.id)}`)}
              >
                {monitor.type === 'browser' ? <MonitorSmartphone /> : <Globe />}
                <span className="truncate">{monitor.name}</span>
                <span className="truncate text-xs text-placeholder">{monitor.id}</span>
                <span
                  className={cn(
                    'ml-auto h-2 w-2 shrink-0 rounded-full',
                    statusDotClasses[monitor.status] ?? 'bg-status-pending'
                  )}
                />
              </CommandItem>
            ))}
          </CommandGroup>
        )}
        <CommandSeparator />
        <CommandGroup heading={t.pages}>
          {navigation.map((item) => (
            <CommandItem key={item.to} value={`page ${item.label} ${item.labelRu}`} onSelect={() => go(item.to)}>
              <item.icon />
              {navLabel(item, lang)}
            </CommandItem>
          ))}
        </CommandGroup>
      </CommandList>
    </CommandDialog>
  );
}
