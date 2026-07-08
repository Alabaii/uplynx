from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, EmailStr, Field, field_validator

MonitorType = Literal["http", "browser"]
MonitorStatus = Literal["up", "down", "paused", "degraded", "pending"]
BrowserAction = Literal["goto", "click", "type", "assert_text"]
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


class UserRead(BaseModel):
    id: int
    email: EmailStr

    model_config = {"from_attributes": True}


class UserOrganizationRead(BaseModel):
    id: int
    name: str
    slug: str
    role: str


class MeRead(UserRead):
    organization: UserOrganizationRead


class OrgRead(BaseModel):
    id: int
    name: str
    slug: str
    role: OrgRole


class OrgCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    slug: str = Field(min_length=1, max_length=160, pattern=r"^[a-z0-9][a-z0-9-]*$")


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


class BrowserStep(BaseModel):
    action: BrowserAction
    url: str | None = None
    selector: str | None = None
    text: str | None = None
    value: str | None = None


class ExpectedHttp(BaseModel):
    status: int | None = Field(default=None, ge=100, le=599)
    body_contains: str | None = None


class ConfigMonitor(BaseModel):
    id: str = Field(min_length=1, max_length=160, pattern=r"^[a-zA-Z0-9_.:-]+$")
    name: str | None = Field(default=None, max_length=200)
    type: MonitorType
    url: str | None = None
    interval: int = Field(ge=10, le=86400)
    expected: ExpectedHttp | None = None
    steps: list[BrowserStep] | None = None
    enabled: bool = True

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


class MonitorUpdate(BaseModel):
    name: str | None = None
    url: str | None = None
    interval: int | None = Field(default=None, ge=10, le=86400)
    expected: ExpectedHttp | None = None
    steps: list[BrowserStep] | None = None
    enabled: bool | None = None
    status: MonitorStatus | None = None


class MonitorRead(BaseModel):
    id: str
    internal_id: int
    name: str
    type: MonitorType
    status: MonitorStatus
    url: str | None
    interval: int
    enabled: bool
    config: dict[str, Any]


class CheckResultRead(BaseModel):
    id: int
    monitor_id: int
    monitor_slug: str
    status: MonitorStatus
    response_time_ms: int | None
    error: str | None
    details: dict[str, Any]
    timestamp: datetime


class MonitorUptimeRead(BaseModel):
    monitor_id: str
    uptime_pct: float | None
    checks_total: int
    avg_response_ms: int | None
    last_check_at: datetime | None
    last_status: MonitorStatus | None
    last_response_ms: int | None


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


class DeploymentLimits(BaseModel):
    max_users: int
    max_monitors: int


class MetaRead(BaseModel):
    deployment_mode: Literal["team", "enterprise"]
    limits: DeploymentLimits | None = None
