import { useEffect, useState } from 'react';
import { KeyRound, ShieldCheck, Trash2 } from 'lucide-react';
import { Button } from '../components/ui/Button';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/Card';
import { Input } from '../components/ui/Input';
import { ApiError, deleteSecret, getMe, listSecrets, upsertSecret, type OrgSecret } from '../api';
import { formatRelativeTime } from '../utils/time';
import { useTexts } from '../i18n';

export default function Secrets() {
  const t = useTexts({
    ru: {
      section: 'Секреты воркспейса',
      title: 'Пароли для браузерных сценариев',
      description:
        'Значения нужны шагам сценария — логин, токен, код. Они шифруются, принадлежат только этому воркспейсу и не показываются после сохранения: ни в списке, ни в истории проверок, ни в аудит-логе.',
      usage: 'Использование в шаге',
      usageHint: 'Сошлитесь на секрет по имени в любом поле шага — url, selector, text, value, contains.',
      addTitle: 'Добавить или заменить',
      nameLabel: 'Имя',
      nameHint: 'Заглавные буквы, цифры и подчёркивание: SHOP_PASSWORD',
      valueLabel: 'Значение',
      save: 'Сохранить',
      saved: (name: string) => `Секрет ${name} сохранён.`,
      saveError: 'Не удалось сохранить секрет.',
      deleted: (name: string) => `Секрет ${name} удалён.`,
      deleteError: 'Не удалось удалить секрет.',
      listTitle: 'Секреты организации',
      empty: 'Секретов пока нет.',
      emptyHint: 'Пока их нет, сценарий с ${...} упадёт с ошибкой «secret is not defined».',
      updated: 'Обновлён',
      author: 'Добавил',
      remove: 'Удалить',
      confirmDelete: (name: string) => `Удалить секрет ${name}? Сценарии, которые на него ссылаются, начнут падать.`,
      readOnly: 'Менять секреты может администратор воркспейса.',
      loadError: 'Не удалось загрузить список секретов.',
    },
    en: {
      section: 'Workspace secrets',
      title: 'Credentials for browser scenarios',
      description:
        'Scenario steps need values like a login, token, or code. They are encrypted, belong to this workspace only, and are never shown again after saving — not in this list, not in check history, not in the audit log.',
      usage: 'Using a secret in a step',
      usageHint: 'Reference a secret by name in any step field — url, selector, text, value, contains.',
      addTitle: 'Add or replace',
      nameLabel: 'Name',
      nameHint: 'Uppercase letters, digits and underscore: SHOP_PASSWORD',
      valueLabel: 'Value',
      save: 'Save',
      saved: (name: string) => `Secret ${name} saved.`,
      saveError: 'Unable to save the secret.',
      deleted: (name: string) => `Secret ${name} deleted.`,
      deleteError: 'Unable to delete the secret.',
      listTitle: 'Organization secrets',
      empty: 'No secrets yet.',
      emptyHint: 'Until one exists, a scenario using ${...} fails with "secret is not defined".',
      updated: 'Updated',
      author: 'Added by',
      remove: 'Delete',
      confirmDelete: (name: string) => `Delete secret ${name}? Scenarios referencing it will start failing.`,
      readOnly: 'Only a workspace admin can change secrets.',
      loadError: 'Unable to load the secret list.',
    },
  });

  const [secrets, setSecrets] = useState<OrgSecret[]>([]);
  const [name, setName] = useState('');
  const [value, setValue] = useState('');
  const [canManage, setCanManage] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [message, setMessage] = useState<{ tone: 'success' | 'error'; text: string } | null>(null);

  useEffect(() => {
    let ignore = false;

    listSecrets()
      .then((items) => !ignore && setSecrets(items))
      .catch(() => !ignore && setMessage({ tone: 'error', text: t.loadError }));

    getMe()
      .then((me) => !ignore && setCanManage(['admin', 'owner'].includes(me.organization?.role ?? '')))
      .catch(() => {
        // роль неизвестна — форма останется скрытой, список всё равно виден
      });

    return () => {
      ignore = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const handleSave = async (event: React.FormEvent) => {
    event.preventDefault();
    setIsSaving(true);
    setMessage(null);

    try {
      const saved = await upsertSecret(name, value);
      setSecrets((current) => [...current.filter((item) => item.name !== saved.name), saved].sort((a, b) => a.name.localeCompare(b.name)));
      setMessage({ tone: 'success', text: t.saved(saved.name) });
      setName('');
      setValue('');
    } catch (error) {
      setMessage({ tone: 'error', text: error instanceof ApiError ? error.message : t.saveError });
    } finally {
      setIsSaving(false);
    }
  };

  const handleDelete = async (secretName: string) => {
    if (!window.confirm(t.confirmDelete(secretName))) {
      return;
    }

    try {
      await deleteSecret(secretName);
      setSecrets((current) => current.filter((item) => item.name !== secretName));
      setMessage({ tone: 'success', text: t.deleted(secretName) });
    } catch (error) {
      setMessage({ tone: 'error', text: error instanceof ApiError ? error.message : t.deleteError });
    }
  };

  return (
    <div className="space-y-6">
      <section className="rounded-lg bg-card p-6 shadow-card">
        <p className="text-sm font-semibold text-primary">{t.section}</p>
        <h1 className="mt-2 text-2xl font-semibold leading-8 text-foreground">{t.title}</h1>
        <p className="mt-3 max-w-3xl text-sm leading-5 text-muted-foreground">{t.description}</p>

        <div className="mt-5 rounded-lg bg-secondary p-4">
          <p className="text-sm font-semibold text-foreground">{t.usage}</p>
          <p className="mt-1 text-sm text-muted-foreground">{t.usageHint}</p>
          <pre className="mt-3 overflow-x-auto rounded-md bg-card p-3 text-xs leading-5 text-foreground">
{`- action: type
  selector: "#password"
  value: "\${SHOP_PASSWORD}"`}
          </pre>
        </div>
      </section>

      {message && (
        <div
          className={
            message.tone === 'success'
              ? 'rounded-lg bg-accent px-4 py-3 text-sm text-accent-foreground'
              : 'rounded-lg bg-status-down/10 px-4 py-3 text-sm text-status-down'
          }
        >
          {message.text}
        </div>
      )}

      <div className="grid gap-6 xl:grid-cols-[0.9fr_1fr]">
        <Card className="overflow-hidden">
          <CardHeader className="border-b border-border">
            <CardTitle className="flex items-center gap-2">
              <KeyRound className="h-5 w-5 text-primary" />
              {t.addTitle}
            </CardTitle>
          </CardHeader>
          <CardContent className="p-6">
            {canManage ? (
              <form onSubmit={handleSave} className="space-y-4">
                <Input
                  label={t.nameLabel}
                  value={name}
                  onChange={(event) => setName(event.target.value.toUpperCase())}
                  placeholder="SHOP_PASSWORD"
                  pattern="[A-Z][A-Z0-9_]*"
                  title={t.nameHint}
                  required
                />
                <p className="text-xs text-muted-foreground">{t.nameHint}</p>
                <Input
                  label={t.valueLabel}
                  type="password"
                  value={value}
                  onChange={(event) => setValue(event.target.value)}
                  autoComplete="new-password"
                  required
                />
                <Button type="submit" disabled={isSaving}>
                  {t.save}
                </Button>
              </form>
            ) : (
              <p className="text-sm text-muted-foreground">{t.readOnly}</p>
            )}
          </CardContent>
        </Card>

        <Card className="overflow-hidden">
          <CardHeader className="border-b border-border">
            <CardTitle className="flex items-center gap-2">
              <ShieldCheck className="h-5 w-5 text-primary" />
              {t.listTitle}
            </CardTitle>
          </CardHeader>
          <CardContent className="p-6">
            {secrets.length === 0 ? (
              <div className="text-sm text-muted-foreground">
                <p>{t.empty}</p>
                <p className="mt-1 text-xs">{t.emptyHint}</p>
              </div>
            ) : (
              <ul className="divide-y divide-border">
                {secrets.map((secret) => (
                  <li key={secret.name} className="flex items-center justify-between gap-4 py-3 first:pt-0 last:pb-0">
                    <div className="min-w-0">
                      <p className="truncate font-mono text-sm font-semibold text-foreground">{secret.name}</p>
                      <p className="mt-1 text-xs text-muted-foreground">
                        {t.updated}: {formatRelativeTime(secret.updated_at)}
                        {secret.created_by_email ? ` · ${t.author}: ${secret.created_by_email}` : ''}
                      </p>
                    </div>
                    {canManage && (
                      <Button
                        type="button"
                        variant="danger"
                        onClick={() => handleDelete(secret.name)}
                        aria-label={`${t.remove} ${secret.name}`}
                      >
                        <Trash2 className="h-4 w-4" />
                      </Button>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
