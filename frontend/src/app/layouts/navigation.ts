import {
  FileCode2,
  KeyRound,
  LayoutDashboard,
  PlusCircle,
  Send,
  Siren,
  Users,
  Wrench,
} from 'lucide-react';
import type { Lang } from '../i18n';

export const navigation = [
  { to: '/', label: 'Dashboard', labelRu: 'Дашборд', icon: LayoutDashboard },
  { to: '/incidents', label: 'Incidents', labelRu: 'Инциденты', icon: Siren },
  { to: '/maintenance', label: 'Maintenance', labelRu: 'Обслуживание', icon: Wrench },
  { to: '/config', label: 'Config', labelRu: 'Конфиг', icon: FileCode2 },
  { to: '/monitors/new', label: 'New Monitor', labelRu: 'Новый монитор', icon: PlusCircle },
  { to: '/team', label: 'Team', labelRu: 'Команда', icon: Users },
  { to: '/telegram', label: 'Telegram', labelRu: 'Telegram', icon: Send },
  { to: '/secrets', label: 'Secrets', labelRu: 'Секреты', icon: KeyRound },
];

export function navLabel(item: { label: string; labelRu: string }, lang: Lang): string {
  return lang === 'ru' ? item.labelRu : item.label;
}
