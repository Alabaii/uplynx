import React, { useEffect, useRef, useState } from 'react';
import { Check, ChevronsUpDown, Plus } from 'lucide-react';
import { Button } from '../components/ui/Button';
import { Input } from '../components/ui/Input';
import { ApiError, createOrg, listOrgs, switchOrg, type Org } from '../api';
import { createSession, getSessionEmail } from '../auth';
import { useTexts } from '../i18n';
import { cn } from '../utils/cn';

const SLUG_PATTERN = /^[a-z0-9-]+$/;

function slugify(value: string) {
  return value
    .toLowerCase()
    .trim()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '');
}

async function switchAndReload(orgId: number) {
  const token = await switchOrg(orgId);
  createSession(token.access_token, getSessionEmail() ?? undefined);
  window.location.assign('/');
}

export function OrgSwitcher({ orgName, currentOrgId }: { orgName: string; currentOrgId: number | null }) {
  const t = useTexts({
    ru: {
      activeWorkspace: 'Текущее рабочее пространство',
      yourOrgs: 'Ваши организации',
      loading: 'Загрузка...',
      createOrg: 'Создать организацию',
    },
    en: {
      activeWorkspace: 'Active workspace',
      yourOrgs: 'Your organizations',
      loading: 'Loading...',
      createOrg: 'Create organization',
    },
  });
  const [isOpen, setIsOpen] = useState(false);
  const [orgs, setOrgs] = useState<Org[]>([]);
  const [isCreateOpen, setIsCreateOpen] = useState(false);
  const [switchingId, setSwitchingId] = useState<number | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!isOpen) {
      return;
    }

    let ignore = false;

    listOrgs()
      .then((rows) => {
        if (!ignore) {
          setOrgs(rows);
        }
      })
      .catch(() => {
        // список недоступен — dropdown покажет только создание
      });

    return () => {
      ignore = true;
    };
  }, [isOpen]);

  useEffect(() => {
    if (!isOpen) {
      return;
    }

    const onMouseDown = (event: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(event.target as Node)) {
        setIsOpen(false);
      }
    };

    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        setIsOpen(false);
      }
    };

    document.addEventListener('mousedown', onMouseDown);
    document.addEventListener('keydown', onKeyDown);

    return () => {
      document.removeEventListener('mousedown', onMouseDown);
      document.removeEventListener('keydown', onKeyDown);
    };
  }, [isOpen]);

  const handleSwitch = async (org: Org) => {
    if (org.id === currentOrgId) {
      setIsOpen(false);
      return;
    }

    setSwitchingId(org.id);

    try {
      await switchAndReload(org.id);
    } catch {
      setSwitchingId(null);
    }
  };

  return (
    <div ref={containerRef} className="relative">
      <button
        type="button"
        onClick={() => setIsOpen((open) => !open)}
        className="flex w-full items-center justify-between gap-2 text-left"
        aria-haspopup="menu"
        aria-expanded={isOpen}
      >
        <span className="min-w-0">
          <span className="block text-xs text-placeholder">{t.activeWorkspace}</span>
          <span className="mt-1 block truncate text-sm font-semibold text-foreground">{orgName}</span>
        </span>
        <ChevronsUpDown className="h-4 w-4 shrink-0 text-muted-foreground" />
      </button>

      {isOpen && (
        <div
          className="absolute left-0 right-0 top-full z-50 mt-2 rounded-lg bg-card p-1.5 shadow-dropdown"
          role="menu"
        >
          <p className="px-2.5 py-1.5 text-[11px] font-semibold uppercase tracking-wide text-placeholder">
            {t.yourOrgs}
          </p>
          {orgs.length === 0 ? (
            <p className="px-2.5 py-2 text-sm text-muted-foreground">{t.loading}</p>
          ) : (
            <ul className="max-h-64 space-y-0.5 overflow-y-auto">
              {orgs.map((org) => {
                const isCurrent = org.id === currentOrgId;

                return (
                  <li key={org.id}>
                    <button
                      type="button"
                      onClick={() => handleSwitch(org)}
                      disabled={switchingId !== null}
                      className={cn(
                        'flex w-full items-center justify-between gap-2 rounded-lg px-2.5 py-2 text-left text-sm transition-colors disabled:opacity-60',
                        isCurrent ? 'bg-accent text-primary' : 'text-foreground hover:bg-secondary'
                      )}
                      role="menuitem"
                    >
                      <span className="flex min-w-0 items-center gap-2">
                        <Check className={cn('h-4 w-4 shrink-0', isCurrent ? 'opacity-100' : 'opacity-0')} />
                        <span className="truncate font-medium">{org.name}</span>
                      </span>
                      <span className="shrink-0 text-xs capitalize text-muted-foreground">{org.role}</span>
                    </button>
                  </li>
                );
              })}
            </ul>
          )}
          <div className="mt-1 border-t border-border pt-1">
            <button
              type="button"
              onClick={() => {
                setIsOpen(false);
                setIsCreateOpen(true);
              }}
              className="flex w-full items-center gap-2 rounded-lg px-2.5 py-2 text-sm font-medium text-primary transition-colors hover:bg-accent"
              role="menuitem"
            >
              <Plus className="h-4 w-4" />
              {t.createOrg}
            </button>
          </div>
        </div>
      )}

      {isCreateOpen && <CreateOrgModal onClose={() => setIsCreateOpen(false)} />}
    </div>
  );
}

function CreateOrgModal({ onClose }: { onClose: () => void }) {
  const t = useTexts({
    ru: {
      title: 'Создать организацию',
      subtitle: 'Вы станете владельцем и переключитесь на новое рабочее пространство.',
      nameLabel: 'Название',
      slugLabel: 'Slug',
      slugError: 'Slug может содержать только строчные латинские буквы, цифры и дефисы.',
      createFailed: 'Не удалось создать организацию',
      cancel: 'Отмена',
      create: 'Создать',
    },
    en: {
      title: 'Create organization',
      subtitle: 'You will become the owner and switch to the new workspace.',
      nameLabel: 'Name',
      slugLabel: 'Slug',
      slugError: 'Slug can only contain lowercase letters, numbers, and dashes.',
      createFailed: 'Unable to create organization',
      cancel: 'Cancel',
      create: 'Create',
    },
  });
  const [name, setName] = useState('');
  const [slug, setSlug] = useState('');
  const [slugEdited, setSlugEdited] = useState(false);
  const [error, setError] = useState('');
  const [isSaving, setIsSaving] = useState(false);

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape' && !isSaving) {
        onClose();
      }
    };

    document.addEventListener('keydown', onKeyDown);

    return () => {
      document.removeEventListener('keydown', onKeyDown);
    };
  }, [isSaving, onClose]);

  const handleNameChange = (value: string) => {
    setName(value);

    if (!slugEdited) {
      setSlug(slugify(value));
    }
  };

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();

    if (!SLUG_PATTERN.test(slug)) {
      setError(t.slugError);
      return;
    }

    setIsSaving(true);
    setError('');

    try {
      const org = await createOrg({ name, slug });
      await switchAndReload(org.id);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : t.createFailed);
      setIsSaving(false);
    }
  };

  return (
    <div
      className="fixed inset-0 z-[60] flex items-center justify-center bg-foreground/40 p-4"
      role="dialog"
      aria-modal="true"
    >
      <div className="w-full max-w-md rounded-lg bg-card p-6 shadow-floating">
        <h2 className="text-lg font-semibold text-foreground">{t.title}</h2>
        <p className="mt-1 text-sm text-muted-foreground">
          {t.subtitle}
        </p>

        <form onSubmit={handleSubmit} className="mt-5 space-y-4">
          <Input
            label={t.nameLabel}
            value={name}
            onChange={(event) => handleNameChange(event.target.value)}
            placeholder="Acme Inc."
            required
            autoFocus
          />
          <Input
            label={t.slugLabel}
            value={slug}
            onChange={(event) => {
              setSlugEdited(true);
              setSlug(event.target.value);
            }}
            placeholder="acme-inc"
            required
          />

          {error && <div className="rounded-lg bg-destructive/10 p-3 text-sm text-destructive">{error}</div>}

          <div className="flex justify-end gap-2 pt-1">
            <Button type="button" variant="ghost" onClick={onClose} disabled={isSaving}>
              {t.cancel}
            </Button>
            <Button type="submit" isLoading={isSaving}>
              {t.create}
            </Button>
          </div>
        </form>
      </div>
    </div>
  );
}
