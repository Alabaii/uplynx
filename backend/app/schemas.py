from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator

MonitorType = Literal["http", "browser"]
MonitorStatus = Literal["up", "down", "paused", "degraded", "pending"]
IncidentStatus = Literal["open", "resolved"]
IncidentSeverity = Literal["down", "degraded"]
BrowserAction = Literal["goto", "click", "type", "assert_text", "wait_for", "assert_url"]
OrgRole = Literal["owner", "admin", "member", "viewer"]
# owner назначается только при создании организации; передача владения — вне скоупа
AssignableOrgRole = Literal["admin", "member", "viewer"]


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=200)


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str = Field(min_length=1, max_length=200)
    new_password: str = Field(min_length=8, max_length=200)


class UserRead(BaseModel):
    id: int
    email: EmailStr

    model_config = {"from_attributes": True}


class UserOrganizationRead(BaseModel):
    id: int
    name: str
    slug: str
    role: str
    status_page_enabled: bool


class MeRead(UserRead):
    organization: UserOrganizationRead


class OrgRead(BaseModel):
    id: int
    name: str
    slug: str
    role: OrgRole
    quota_monitors: int | None = None
    quota_members: int | None = None
    status_page_enabled: bool = False
    alert_emails: list[str] = Field(default_factory=list)


class OrgCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    slug: str = Field(min_length=1, max_length=160, pattern=r"^[a-z0-9][a-z0-9-]*$")


class OrgUpdate(BaseModel):
    # null для квоты значим (снять лимит), поэтому обработка через exclude_unset
    name: str | None = Field(default=None, min_length=1, max_length=200)
    quota_monitors: int | None = Field(default=None, ge=0)
    quota_members: int | None = Field(default=None, ge=1)
    status_page_enabled: bool | None = None
    alert_emails: list[EmailStr] | None = Field(default=None, max_length=10)


class OrgMemberRead(BaseModel):
    user_id: int
    email: EmailStr
    role: OrgRole
    created_at: datetime


class OrgMemberAdd(BaseModel):
    email: EmailStr
    role: AssignableOrgRole = "member"


class OrgMemberUpdate(BaseModel):
    role: AssignableOrgRole


class AuditLogRead(BaseModel):
    id: int
    action: str
    entity: str
    entity_id: str
    payload: dict[str, Any]
    created_at: datetime
    actor_email: str | None = None


class BrowserStep(BaseModel):
    action: BrowserAction
    url: str | None = None
    selector: str | None = None
    text: str | None = None
    value: str | None = None
    contains: str | None = None


class ExpectedHttp(BaseModel):
    status: int | None = Field(default=None, ge=100, le=599)
    body_contains: str | None = None
    response_time_ms: int | None = Field(default=None, ge=1)


class ConfigMonitor(BaseModel):
    id: str = Field(min_length=1, max_length=160, pattern=r"^[a-zA-Z0-9_.:-]+$")
    name: str | None = Field(default=None, max_length=200)
    type: MonitorType
    url: str | None = None
    interval: int = Field(ge=10, le=86400)
    expected: ExpectedHttp | None = None
    steps: list[BrowserStep] | None = None
    enabled: bool = True
    # анти-флаппинг: статус меняется после N одинаковых результатов подряд
    confirmations: int = Field(default=1, ge=1, le=10)
    # повторные алерты каждые N минут, пока монитор down/degraded; None — выключено
    renotify_interval_minutes: int | None = Field(default=None, ge=1, le=1440)

    @field_validator("steps")
    @classmethod
    def browser_steps_required(cls, value: list[BrowserStep] | None, info: Any) -> list[BrowserStep] | None:
        if info.data.get("type") == "browser" and not value:
            raise ValueError("browser monitor requires steps")
        return value

    @field_validator("url")
    @classmethod
    def http_url_required(cls, value: str | None, info: Any) -> str | None:
        if info.data.get("type") == "http" and not value:
            raise ValueError("http monitor requires url")
        return value


class ConfigDocument(BaseModel):
    version: int = 1
    monitors: list[ConfigMonitor] = Field(default_factory=list)


class ConfigUpload(BaseModel):
    content: str
    format: Literal["yaml", "json"] = "yaml"


class ConfigRead(BaseModel):
    content: str
    format: str
    version: int | None = None


class ConfigVersionRead(BaseModel):
    id: int
    version: int
    format: str
    created_at: datetime

    model_config = {"from_attributes": True}


class ConfigRollback(BaseModel):
    version: int


class MonitorCreate(BaseModel):
    id: str = Field(min_length=1, max_length=160, pattern=r"^[a-zA-Z0-9_.:-]+$")
    name: str | None = None
    type: MonitorType
    url: str | None = None
    interval: int = Field(ge=10, le=86400)
    expected: ExpectedHttp | None = None
    steps: list[BrowserStep] | None = None
    enabled: bool = True
    confirmations: int = Field(default=1, ge=1, le=10)
    renotify_interval_minutes: int | None = Field(default=None, ge=1, le=1440)


class MonitorUpdate(BaseModel):
    name: str | None = None
    url: str | None = None
    interval: int | None = Field(default=None, ge=10, le=86400)
    expected: ExpectedHttp | None = None
    steps: list[BrowserStep] | None = None
    enabled: bool | None = None
    status: MonitorStatus | None = None
    confirmations: int | None = Field(default=None, ge=1, le=10)
    renotify_interval_minutes: int | None = Field(default=None, ge=1, le=1440)


class MonitorRead(BaseModel):
    id: str
    internal_id: int
    name: str
    type: MonitorType
    status: MonitorStatus
    url: str | None
    interval: int
    enabled: bool
    confirmations: int = 1
    config: dict[str, Any]
    in_maintenance: bool = False


class CheckResultRead(BaseModel):
    id: int
    monitor_id: int
    monitor_slug: str
    status: MonitorStatus
    response_time_ms: int | None
    error: str | None
    details: dict[str, Any]
    timestamp: datetime


class CheckNowRead(BaseModel):
    queued: bool
    task_id: str


class IncidentRead(BaseModel):
    id: int
    monitor_slug: str
    monitor_name: str
    status: IncidentStatus
    severity: IncidentSeverity
    started_at: datetime
    resolved_at: datetime | None
    duration_seconds: int | None
    trigger_error: str | None


class MaintenanceWindowCreate(BaseModel):
    # monitor_id — slug монитора; null — окно на всю организацию
    monitor_id: str | None = None
    starts_at: datetime
    ends_at: datetime
    note: str | None = Field(default=None, max_length=300)

    @model_validator(mode="after")
    def window_must_end_in_future(self) -> "MaintenanceWindowCreate":
        starts = self.starts_at if self.starts_at.tzinfo else self.starts_at.replace(tzinfo=timezone.utc)
        ends = self.ends_at if self.ends_at.tzinfo else self.ends_at.replace(tzinfo=timezone.utc)
        if ends <= starts:
            raise ValueError("ends_at must be after starts_at")
        if ends <= datetime.now(timezone.utc):
            raise ValueError("window must not be entirely in the past")
        return self


class MaintenanceWindowRead(BaseModel):
    id: int
    monitor_id: str | None
    monitor_name: str | None
    starts_at: datetime
    ends_at: datetime
    note: str | None
    active: bool
    created_by_email: str | None


class MonitorUptimeRead(BaseModel):
    monitor_id: str
    uptime_pct: float | None
    checks_total: int
    avg_response_ms: int | None
    last_check_at: datetime | None
    last_status: MonitorStatus | None
    last_response_ms: int | None


PublicOverallStatus = Literal["operational", "degraded", "down"]


class PublicStatusMonitor(BaseModel):
    # публичная страница: только имя и статус, никаких url/slug/id
    name: str
    status: MonitorStatus
    uptime_pct: float | None
    last_check_at: datetime | None
    in_maintenance: bool = False


class PublicStatusRead(BaseModel):
    organization: str
    updated_at: datetime
    overall: PublicOverallStatus
    monitors: list[PublicStatusMonitor]


class CheckTask(BaseModel):
    task_id: str
    monitor_id: int
    type: MonitorType
    url: str | None = None
    config: dict[str, Any] = Field(default_factory=dict)
    timeout_seconds: int = 30
    created_at: datetime
    attempt: int = 1


class TelegramConnect(BaseModel):
    bot_token: str = Field(min_length=10, max_length=512)
    chat_id: str = Field(min_length=1, max_length=120)
    alert_scopes: list[Literal["down", "degraded", "recovered"]] = ["down", "recovered"]


class TelegramRead(BaseModel):
    connected: bool
    chat_id: str | None = None
    alert_scopes: list[str] = Field(default_factory=list)
    bot_token_masked: str | None = None


class TelegramTestResponse(BaseModel):
    ok: bool
    detail: str


class PushConfigRead(BaseModel):
    enabled: bool
    public_key: str | None = None


class PushSubscriptionKeys(BaseModel):
    p256dh: str = Field(min_length=1, max_length=255)
    auth: str = Field(min_length=1, max_length=255)


class PushSubscribe(BaseModel):
    endpoint: str = Field(min_length=1, max_length=2048)
    keys: PushSubscriptionKeys


class PushUnsubscribe(BaseModel):
    endpoint: str = Field(min_length=1, max_length=2048)


class DeploymentLimits(BaseModel):
    max_users: int
    max_monitors: int


class MetaRead(BaseModel):
    deployment_mode: Literal["team", "enterprise"]
    limits: DeploymentLimits | None = None
    email_enabled: bool = False
