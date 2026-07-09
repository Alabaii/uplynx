import { useEffect, useState } from 'react';
import { Activity, ExternalLink, Globe, Trash2, UserPlus, Users } from 'lucide-react';
import { Button } from '../components/ui/Button';
import { Card, CardContent, CardHeader, CardTitle } from '../components/ui/Card';
import { Input } from '../components/ui/Input';
import {
  ApiError,
  addOrgMember,
  getMe,
  listAuditEvents,
  listOrgMembers,
  removeOrgMember,
  updateCurrentOrg,
  updateMemberRole,
  type AuditEvent,
  type OrgMember,
  type OrgRole,
} from '../api';
import { useTexts } from '../i18n';
import { cn } from '../utils/cn';
import { formatRelativeTime } from '../utils/time';

const roleBadgeClasses: Record<OrgRole, string> = {
  owner: 'bg-accent text-primary',
  admin: 'bg-primary/10 text-primary',
  member: 'bg-secondary text-muted-foreground',
  viewer: 'bg-muted text-muted-foreground',
};

const assignableRoles = ['viewer', 'member', 'admin'] as const;

const roleTexts: { ru: Record<OrgRole, string>; en: Record<OrgRole, string> } = {
  ru: { owner: 'владелец', admin: 'админ', member: 'участник', viewer: 'наблюдатель' },
  en: { owner: 'owner', admin: 'admin', member: 'member', viewer: 'viewer' },
};

function RoleBadge({ role }: { role: OrgRole }) {
  const roles = useTexts(roleTexts);
  return (
    <span
      className={cn(
        'inline-flex items-center rounded-lg px-2.5 py-1 text-xs font-semibold capitalize',
        roleBadgeClasses[role]
      )}
    >
      {roles[role]}
    </span>
  );
}

export default function Team() {
  const roles = useTexts(roleTexts);
  const t = useTexts({
    ru: {
      team: 'Команда',
      membersOf: (org: string) => `Участники ${org}`,
      headerDescription:
        'У всех здесь общие мониторы, конфигурация и оповещения. Роли определяют, кто что может изменять.',
      yourRole: 'Ваша роль:',
      myTeam: 'Моя команда',
      addMember: 'Добавить участника',
      emailLabel: 'Email зарегистрированного пользователя',
      roleFieldLabel: 'Роль',
      membersTitle: 'Участники',
      loadingMembers: 'Загрузка участников...',
      you: 'Вы',
      joined: (date: string) => `В команде с ${date}`,
      roleOf: (email: string) => `Роль ${email}`,
      remove: 'Удалить',
      confirmRemove: (email: string) => `Удалить ${email} из рабочего пространства?`,
      added: (email: string, role: string) => `Добавили ${email} с ролью ${role}.`,
      roleChanged: (email: string, role: string) => `Теперь роль ${email} — ${role}.`,
      removed: (email: string) => `Удалили ${email}.`,
      loadError: 'Не удалось загрузить участников',
      addError: 'Не удалось добавить участника',
      roleChangeError: 'Не удалось изменить роль',
      removeError: 'Не удалось удалить участника',
      statusPageTitle: 'Публичная статус-страница',
      statusPageDescription:
        'Поделитесь страницей только для чтения с текущим статусом ваших мониторов. Вход не требуется, URL мониторов остаются скрытыми.',
      statusPageUpdateError: 'Не удалось обновить статус-страницу',
      disableStatusPage: 'Выключить статус-страницу',
      enableStatusPage: 'Включить статус-страницу',
      openStatus: (slug: string) => `Открыть /status/${slug}`,
      recentActivity: 'Недавняя активность',
      noActivity: 'Пока нет активности.',
      system: 'Система',
      auditActions: {
        'monitor.create': 'создал(а) монитор',
        'monitor.update': 'обновил(а) монитор',
        'monitor.delete': 'удалил(а) монитор',
        'config.upload': 'загрузил(а) конфиг',
        'config.rollback': 'откатил(а) конфиг',
        'telegram.connect': 'подключил(а) Telegram',
        'org.create': 'создал(а) организацию',
        'org.update': 'обновил(а) настройки организации',
        'member.add': 'добавил(а) участника',
        'member.role_change': 'изменил(а) роль участника',
        'member.remove': 'удалил(а) участника',
        'auth.register': 'присоединился(ась) к рабочему пространству',
      } as Record<string, string>,
    },
    en: {
      team: 'Team',
      membersOf: (org: string) => `Members of ${org}`,
      headerDescription:
        'Everyone here shares the same monitors, config, and alerts. Roles control who can edit what.',
      yourRole: 'Your role:',
      myTeam: 'My team',
      addMember: 'Add member',
      emailLabel: 'Email of a registered user',
      roleFieldLabel: 'Role',
      membersTitle: 'Members',
      loadingMembers: 'Loading members...',
      you: 'You',
      joined: (date: string) => `Joined ${date}`,
      roleOf: (email: string) => `Role of ${email}`,
      remove: 'Remove',
      confirmRemove: (email: string) => `Remove ${email} from the workspace?`,
      added: (email: string, role: string) => `Added ${email} as ${role}.`,
      roleChanged: (email: string, role: string) => `${email} is now ${role}.`,
      removed: (email: string) => `Removed ${email}.`,
      loadError: 'Unable to load team members',
      addError: 'Unable to add member',
      roleChangeError: 'Unable to change role',
      removeError: 'Unable to remove member',
      statusPageTitle: 'Public status page',
      statusPageDescription:
        'Share a read-only page with the live status of your monitors. No sign-in required, monitor URLs stay private.',
      statusPageUpdateError: 'Unable to update the status page',
      disableStatusPage: 'Disable status page',
      enableStatusPage: 'Enable status page',
      openStatus: (slug: string) => `Open /status/${slug}`,
      recentActivity: 'Recent activity',
      noActivity: 'No activity yet.',
      system: 'System',
      auditActions: {
        'monitor.create': 'created monitor',
        'monitor.update': 'updated monitor',
        'monitor.delete': 'deleted monitor',
        'config.upload': 'uploaded config',
        'config.rollback': 'rolled back config',
        'telegram.connect': 'connected Telegram',
        'org.create': 'created organization',
        'org.update': 'updated organization settings',
        'member.add': 'added member',
        'member.role_change': 'changed member role',
        'member.remove': 'removed member',
        'auth.register': 'joined the workspace',
      } as Record<string, string>,
    },
  });
  const [members, setMembers] = useState<OrgMember[]>([]);
  const [myUserId, setMyUserId] = useState<number | null>(null);
  const [myRole, setMyRole] = useState<OrgRole>('viewer');
  const [orgName, setOrgName] = useState(t.myTeam);
  const [orgSlug, setOrgSlug] = useState('');
  const [statusPageEnabled, setStatusPageEnabled] = useState(false);
  const [statusPageError, setStatusPageError] = useState('');
  const [isTogglingStatusPage, setIsTogglingStatusPage] = useState(false);
  const [newEmail, setNewEmail] = useState('');
  const [newRole, setNewRole] = useState<OrgRole>('member');
  const [isAdding, setIsAdding] = useState(false);
  const [message, setMessage] = useState('');
  const [error, setError] = useState('');
  const [auditEvents, setAuditEvents] = useState<AuditEvent[]>([]);

  const canManage = myRole === 'admin' || myRole === 'owner';

  useEffect(() => {
    let ignore = false;

    Promise.all([getMe(), listOrgMembers()])
      .then(([me, memberList]) => {
        if (!ignore) {
          setMyUserId(me.id);
          setMyRole(me.organization?.role ?? 'viewer');
          setOrgName(me.organization?.name ?? t.myTeam);
          setOrgSlug(me.organization?.slug ?? '');
          setStatusPageEnabled(me.organization?.status_page_enabled ?? false);
          setMembers(memberList);
          setError('');
        }
      })
      .catch((error) => {
        if (!ignore) {
          setError(error instanceof Error ? error.message : t.loadError);
        }
      });

    return () => {
      ignore = true;
    };
  }, []);

  useEffect(() => {
    if (!canManage) {
      return;
    }

    let ignore = false;

    listAuditEvents(20)
      .then((events) => {
        if (!ignore) {
          setAuditEvents(events);
        }
      })
      .catch(() => {
        // карточка активности вторична — ошибку загрузки не показываем
      });

    return () => {
      ignore = true;
    };
  }, [canManage]);

  const handleAdd = async (event: React.FormEvent) => {
    event.preventDefault();
    setIsAdding(true);
    setMessage('');
    setError('');

    try {
      const added = await addOrgMember(newEmail, newRole);

      setMembers((current) => [...current, added]);
      setNewEmail('');
      setMessage(t.added(added.email, roles[added.role]));
    } catch (error) {
      setError(error instanceof ApiError ? error.message : t.addError);
    } finally {
      setIsAdding(false);
    }
  };

  const handleRoleChange = async (member: OrgMember, role: OrgRole) => {
    setMessage('');
    setError('');

    try {
      const updated = await updateMemberRole(member.user_id, role);

      setMembers((current) => current.map((item) => (item.user_id === updated.user_id ? updated : item)));
      setMessage(t.roleChanged(updated.email, roles[updated.role]));
    } catch (error) {
      setError(error instanceof ApiError ? error.message : t.roleChangeError);
    }
  };

  const handleToggleStatusPage = async () => {
    setIsTogglingStatusPage(true);
    setStatusPageError('');

    try {
      const updated = await updateCurrentOrg({ status_page_enabled: !statusPageEnabled });

      setStatusPageEnabled(updated.status_page_enabled);
    } catch (error) {
      setStatusPageError(error instanceof ApiError ? error.message : t.statusPageUpdateError);
    } finally {
      setIsTogglingStatusPage(false);
    }
  };

  const handleRemove = async (member: OrgMember) => {
    if (!window.confirm(t.confirmRemove(member.email))) {
      return;
    }

    setMessage('');
    setError('');

    try {
      await removeOrgMember(member.user_id);
      setMembers((current) => current.filter((item) => item.user_id !== member.user_id));
      setMessage(t.removed(member.email));
    } catch (error) {
      setError(error instanceof ApiError ? error.message : t.removeError);
    }
  };

  return (
    <div className="space-y-6">
      <section className="rounded-lg bg-card p-6 shadow-card">
        <div className="flex flex-col gap-6 xl:flex-row xl:items-end xl:justify-between">
          <div>
            <p className="text-sm font-semibold text-primary">{t.team}</p>
            <h1 className="mt-2 text-2xl font-semibold leading-8 text-foreground">{t.membersOf(orgName)}</h1>
            <p className="mt-3 max-w-3xl text-sm leading-5 text-muted-foreground">{t.headerDescription}</p>
          </div>

          <div className="rounded-lg bg-secondary px-4 py-3 text-sm text-muted-foreground">
            {t.yourRole} <span className="font-semibold capitalize text-foreground">{roles[myRole]}</span>
          </div>
        </div>
      </section>

      {canManage && (
        <Card>
          <CardHeader className="border-b border-border">
            <CardTitle className="flex items-center gap-2">
              <UserPlus className="h-5 w-5 text-primary" />
              {t.addMember}
            </CardTitle>
          </CardHeader>
          <CardContent className="p-6">
            <form onSubmit={handleAdd} className="flex flex-col gap-4 md:flex-row md:items-end">
              <div className="flex-1">
                <Input
                  label={t.emailLabel}
                  type="email"
                  value={newEmail}
                  onChange={(event) => setNewEmail(event.target.value)}
                  placeholder="teammate@example.com"
                  required
                />
              </div>
              <div>
                <label htmlFor="new-member-role" className="mb-1 block text-sm font-normal text-placeholder">
                  {t.roleFieldLabel}
                </label>
                <select
                  id="new-member-role"
                  value={newRole}
                  onChange={(event) => setNewRole(event.target.value as OrgRole)}
                  className="h-11 rounded-lg border border-input bg-input-background px-3 text-base text-foreground transition-colors hover:border-input-border-hover focus:border-input-border-hover focus:outline-none focus:ring-2 focus:ring-ring/20"
                >
                  {assignableRoles.map((role) => (
                    <option key={role} value={role}>
                      {roles[role]}
                    </option>
                  ))}
                </select>
              </div>
              <Button type="submit" isLoading={isAdding}>
                <UserPlus className="h-4 w-4" />
                {t.addMember}
              </Button>
            </form>
          </CardContent>
        </Card>
      )}

      <Card className="overflow-hidden">
        <CardHeader className="border-b border-border">
          <CardTitle className="flex items-center gap-2">
            <Users className="h-5 w-5 text-primary" />
            {t.membersTitle} ({members.length})
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-3 p-6">
          {message && <div className="rounded-lg bg-accent p-4 text-sm text-accent-foreground">{message}</div>}
          {error && <div className="rounded-lg bg-destructive/10 p-4 text-sm text-destructive">{error}</div>}

          {members.length === 0 && !error ? (
            <div className="rounded-lg bg-secondary p-4 text-sm text-muted-foreground">{t.loadingMembers}</div>
          ) : (
            members.map((member) => {
              const isSelf = member.user_id === myUserId;
              const manageable = canManage && !isSelf && member.role !== 'owner';

              return (
                <div
                  key={member.user_id}
                  className="flex flex-col gap-3 rounded-lg border border-border p-4 sm:flex-row sm:items-center sm:justify-between"
                >
                  <div className="min-w-0">
                    <div className="flex flex-wrap items-center gap-2">
                      <p className="truncate text-sm font-semibold text-foreground">{member.email}</p>
                      <RoleBadge role={member.role} />
                      {isSelf && (
                        <span className="rounded-lg bg-secondary px-2 py-0.5 text-[11px] font-semibold text-muted-foreground">
                          {t.you}
                        </span>
                      )}
                    </div>
                    <p className="mt-1 text-xs text-placeholder">
                      {t.joined(new Date(member.created_at).toLocaleDateString())}
                    </p>
                  </div>

                  {manageable && (
                    <div className="flex shrink-0 items-center gap-2">
                      <select
                        aria-label={t.roleOf(member.email)}
                        value={member.role}
                        onChange={(event) => handleRoleChange(member, event.target.value as OrgRole)}
                        className="h-9 rounded-lg border border-input bg-input-background px-2 text-sm text-foreground transition-colors hover:border-input-border-hover focus:border-input-border-hover focus:outline-none focus:ring-2 focus:ring-ring/20"
                      >
                        {assignableRoles.map((role) => (
                          <option key={role} value={role}>
                            {roles[role]}
                          </option>
                        ))}
                      </select>
                      <Button variant="ghost" size="sm" className="text-destructive" onClick={() => handleRemove(member)}>
                        <Trash2 className="h-4 w-4" />
                        {t.remove}
                      </Button>
                    </div>
                  )}
                </div>
              );
            })
          )}
        </CardContent>
      </Card>

      {myRole === 'owner' && (
        <Card>
          <CardHeader className="border-b border-border">
            <CardTitle className="flex items-center gap-2">
              <Globe className="h-5 w-5 text-primary" />
              {t.statusPageTitle}
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-4 p-6">
            <p className="text-sm text-muted-foreground">{t.statusPageDescription}</p>

            {statusPageError && (
              <div className="rounded-lg bg-destructive/10 p-4 text-sm text-destructive">{statusPageError}</div>
            )}

            <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
              <Button
                variant={statusPageEnabled ? 'outline' : 'primary'}
                isLoading={isTogglingStatusPage}
                onClick={handleToggleStatusPage}
              >
                {statusPageEnabled ? t.disableStatusPage : t.enableStatusPage}
              </Button>
              {statusPageEnabled && orgSlug && (
                <a
                  href={`/status/${orgSlug}`}
                  target="_blank"
                  rel="noreferrer"
                  className="inline-flex items-center gap-1.5 text-sm font-semibold text-primary hover:text-primary-hover"
                >
                  {t.openStatus(orgSlug)}
                  <ExternalLink className="h-4 w-4" />
                </a>
              )}
            </div>
          </CardContent>
        </Card>
      )}

      {canManage && (
        <Card className="overflow-hidden">
          <CardHeader className="border-b border-border">
            <CardTitle className="flex items-center gap-2">
              <Activity className="h-5 w-5 text-primary" />
              {t.recentActivity}
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-3 p-6">
            {auditEvents.length === 0 ? (
              <div className="rounded-lg bg-secondary p-4 text-sm text-muted-foreground">{t.noActivity}</div>
            ) : (
              auditEvents.map((event) => (
                <div
                  key={event.id}
                  className="flex flex-col gap-1 rounded-lg border border-border p-4 sm:flex-row sm:items-center sm:justify-between"
                >
                  <p className="min-w-0 truncate text-sm text-foreground">
                    <span className="font-semibold">{event.actor_email ?? t.system}</span>{' '}
                    <span className="text-muted-foreground">{t.auditActions[event.action] ?? event.action}</span>{' '}
                    <span className="font-semibold">{event.entity_id}</span>
                  </p>
                  <p className="shrink-0 text-xs text-placeholder">{formatRelativeTime(event.created_at)}</p>
                </div>
              ))
            )}
          </CardContent>
        </Card>
      )}
    </div>
  );
}
