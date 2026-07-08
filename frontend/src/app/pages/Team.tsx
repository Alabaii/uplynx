import { useEffect, useState } from 'react';
import { Activity, Trash2, UserPlus, Users } from 'lucide-react';
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
  updateMemberRole,
  type AuditEvent,
  type OrgMember,
  type OrgRole,
} from '../api';
import { cn } from '../utils/cn';
import { formatRelativeTime } from '../utils/time';

const roleBadgeClasses: Record<OrgRole, string> = {
  owner: 'bg-accent text-primary',
  admin: 'bg-primary/10 text-primary',
  member: 'bg-secondary text-muted-foreground',
  viewer: 'bg-muted text-muted-foreground',
};

const assignableRoles = ['viewer', 'member', 'admin'] as const;

const actionLabels: Record<string, string> = {
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
};

function RoleBadge({ role }: { role: OrgRole }) {
  return (
    <span
      className={cn(
        'inline-flex items-center rounded-lg px-2.5 py-1 text-xs font-semibold capitalize',
        roleBadgeClasses[role]
      )}
    >
      {role}
    </span>
  );
}

export default function Team() {
  const [members, setMembers] = useState<OrgMember[]>([]);
  const [myUserId, setMyUserId] = useState<number | null>(null);
  const [myRole, setMyRole] = useState<OrgRole>('viewer');
  const [orgName, setOrgName] = useState('My team');
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
          setOrgName(me.organization?.name ?? 'My team');
          setMembers(memberList);
          setError('');
        }
      })
      .catch((error) => {
        if (!ignore) {
          setError(error instanceof Error ? error.message : 'Unable to load team members');
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
      setMessage(`Added ${added.email} as ${added.role}.`);
    } catch (error) {
      setError(error instanceof ApiError ? error.message : 'Unable to add member');
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
      setMessage(`${updated.email} is now ${updated.role}.`);
    } catch (error) {
      setError(error instanceof ApiError ? error.message : 'Unable to change role');
    }
  };

  const handleRemove = async (member: OrgMember) => {
    if (!window.confirm(`Remove ${member.email} from the workspace?`)) {
      return;
    }

    setMessage('');
    setError('');

    try {
      await removeOrgMember(member.user_id);
      setMembers((current) => current.filter((item) => item.user_id !== member.user_id));
      setMessage(`Removed ${member.email}.`);
    } catch (error) {
      setError(error instanceof ApiError ? error.message : 'Unable to remove member');
    }
  };

  return (
    <div className="space-y-6">
      <section className="rounded-lg bg-card p-6 shadow-card">
        <div className="flex flex-col gap-6 xl:flex-row xl:items-end xl:justify-between">
          <div>
            <p className="text-sm font-semibold text-primary">Team</p>
            <h1 className="mt-2 text-2xl font-semibold leading-8 text-foreground">Members of {orgName}</h1>
            <p className="mt-3 max-w-3xl text-sm leading-5 text-muted-foreground">
              Everyone here shares the same monitors, config, and alerts. Roles control who can edit what.
            </p>
          </div>

          <div className="rounded-lg bg-secondary px-4 py-3 text-sm text-muted-foreground">
            Your role: <span className="font-semibold capitalize text-foreground">{myRole}</span>
          </div>
        </div>
      </section>

      {canManage && (
        <Card>
          <CardHeader className="border-b border-border">
            <CardTitle className="flex items-center gap-2">
              <UserPlus className="h-5 w-5 text-primary" />
              Add member
            </CardTitle>
          </CardHeader>
          <CardContent className="p-6">
            <form onSubmit={handleAdd} className="flex flex-col gap-4 md:flex-row md:items-end">
              <div className="flex-1">
                <Input
                  label="Email of a registered user"
                  type="email"
                  value={newEmail}
                  onChange={(event) => setNewEmail(event.target.value)}
                  placeholder="teammate@example.com"
                  required
                />
              </div>
              <div>
                <label htmlFor="new-member-role" className="mb-1 block text-sm font-normal text-placeholder">
                  Role
                </label>
                <select
                  id="new-member-role"
                  value={newRole}
                  onChange={(event) => setNewRole(event.target.value as OrgRole)}
                  className="h-11 rounded-lg border border-input bg-input-background px-3 text-base text-foreground transition-colors hover:border-input-border-hover focus:border-input-border-hover focus:outline-none focus:ring-2 focus:ring-ring/20"
                >
                  {assignableRoles.map((role) => (
                    <option key={role} value={role}>
                      {role}
                    </option>
                  ))}
                </select>
              </div>
              <Button type="submit" isLoading={isAdding}>
                <UserPlus className="h-4 w-4" />
                Add member
              </Button>
            </form>
          </CardContent>
        </Card>
      )}

      <Card className="overflow-hidden">
        <CardHeader className="border-b border-border">
          <CardTitle className="flex items-center gap-2">
            <Users className="h-5 w-5 text-primary" />
            Members ({members.length})
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-3 p-6">
          {message && <div className="rounded-lg bg-accent p-4 text-sm text-accent-foreground">{message}</div>}
          {error && <div className="rounded-lg bg-destructive/10 p-4 text-sm text-destructive">{error}</div>}

          {members.length === 0 && !error ? (
            <div className="rounded-lg bg-secondary p-4 text-sm text-muted-foreground">Loading members...</div>
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
                          You
                        </span>
                      )}
                    </div>
                    <p className="mt-1 text-xs text-placeholder">
                      Joined {new Date(member.created_at).toLocaleDateString()}
                    </p>
                  </div>

                  {manageable && (
                    <div className="flex shrink-0 items-center gap-2">
                      <select
                        aria-label={`Role of ${member.email}`}
                        value={member.role}
                        onChange={(event) => handleRoleChange(member, event.target.value as OrgRole)}
                        className="h-9 rounded-lg border border-input bg-input-background px-2 text-sm text-foreground transition-colors hover:border-input-border-hover focus:border-input-border-hover focus:outline-none focus:ring-2 focus:ring-ring/20"
                      >
                        {assignableRoles.map((role) => (
                          <option key={role} value={role}>
                            {role}
                          </option>
                        ))}
                      </select>
                      <Button variant="ghost" size="sm" className="text-destructive" onClick={() => handleRemove(member)}>
                        <Trash2 className="h-4 w-4" />
                        Remove
                      </Button>
                    </div>
                  )}
                </div>
              );
            })
          )}
        </CardContent>
      </Card>

      {canManage && (
        <Card className="overflow-hidden">
          <CardHeader className="border-b border-border">
            <CardTitle className="flex items-center gap-2">
              <Activity className="h-5 w-5 text-primary" />
              Recent activity
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-3 p-6">
            {auditEvents.length === 0 ? (
              <div className="rounded-lg bg-secondary p-4 text-sm text-muted-foreground">No activity yet.</div>
            ) : (
              auditEvents.map((event) => (
                <div
                  key={event.id}
                  className="flex flex-col gap-1 rounded-lg border border-border p-4 sm:flex-row sm:items-center sm:justify-between"
                >
                  <p className="min-w-0 truncate text-sm text-foreground">
                    <span className="font-semibold">{event.actor_email ?? 'System'}</span>{' '}
                    <span className="text-muted-foreground">{actionLabels[event.action] ?? event.action}</span>{' '}
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
