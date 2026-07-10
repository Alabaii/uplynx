import { getActiveLang } from '../i18n';

// единицы: [ru, en]
const UNITS = {
  s: ['с', 's'],
  m: ['мин', 'm'],
  h: ['ч', 'h'],
  d: ['дн', 'd'],
} as const;

function unit(key: keyof typeof UNITS): string {
  return UNITS[key][getActiveLang() === 'ru' ? 0 : 1];
}

export function formatRelativeTime(iso: string | null | undefined): string {
  if (!iso) {
    return '—';
  }

  const seconds = Math.max(0, Math.floor((Date.now() - new Date(iso).getTime()) / 1000));
  const ago = getActiveLang() === 'ru' ? 'назад' : 'ago';

  if (seconds < 60) return `${seconds}${unit('s')} ${ago}`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)}${unit('m')} ${ago}`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}${unit('h')} ${ago}`;
  return `${Math.floor(seconds / 86400)}${unit('d')} ${ago}`;
}

export function formatDuration(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined) {
    return '—';
  }

  if (seconds < 60) return `${seconds}${unit('s')}`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)}${unit('m')}`;

  if (seconds < 86400) {
    const hours = Math.floor(seconds / 3600);
    const minutes = Math.floor((seconds % 3600) / 60);
    return minutes ? `${hours}${unit('h')} ${minutes}${unit('m')}` : `${hours}${unit('h')}`;
  }

  const days = Math.floor(seconds / 86400);
  const hours = Math.floor((seconds % 86400) / 3600);
  return hours ? `${days}${unit('d')} ${hours}${unit('h')}` : `${days}${unit('d')}`;
}
