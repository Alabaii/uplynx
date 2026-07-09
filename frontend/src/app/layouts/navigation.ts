import {
  FileCode2,
  LayoutDashboard,
  PlusCircle,
  Send,
  Siren,
  Users,
  Wrench,
} from 'lucide-react';

export const navigation = [
  { to: '/', label: 'Dashboard', icon: LayoutDashboard },
  { to: '/incidents', label: 'Incidents', icon: Siren },
  { to: '/maintenance', label: 'Maintenance', icon: Wrench },
  { to: '/config', label: 'Config', icon: FileCode2 },
  { to: '/monitors/new', label: 'New Monitor', icon: PlusCircle },
  { to: '/team', label: 'Team', icon: Users },
  { to: '/telegram', label: 'Telegram', icon: Send },
];
