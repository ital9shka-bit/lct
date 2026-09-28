from __future__ import annotations

from datetime import date, datetime
import re
from typing import Any, Dict, List, Literal, Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, EmailStr, Field, ValidationInfo, field_validator, model_validator


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class LoginRequest(BaseModel):
    identifier: str = Field(min_length=1, max_length=320)
    password: str = Field(min_length=1, max_length=128)


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    email: EmailStr
    is_demo: bool


class AuthResponse(BaseModel):
    user: UserResponse


class ObjectListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    object_type: str
    address: str
    timezone: str
    is_draft: bool
    is_archived: bool


class CameraInput(BaseModel):
    client_id: Optional[str] = None
    id: Optional[str] = None
    name: str = Field(min_length=1, max_length=80)
    zone: str = Field(default="", max_length=200)
    sort_order: int = Field(default=0, ge=0)
    view_description: str = Field(default="", max_length=1000)
    view_type: Literal["fixed overview", "fixed detail", "ptz preset"] = "fixed overview"
    placement: str = Field(default="", max_length=500)
    orientation: Literal[
        "", "north", "north-east", "east", "south-east", "south", "south-west", "west", "north-west"
    ] = ""
    coverage: List[str] = Field(default_factory=list, max_length=50)

    @field_validator("name", "zone", "view_description", "placement")
    @classmethod
    def trim_text(cls, value: str, info: ValidationInfo) -> str:
        value = value.strip()
        if not value and info.field_name == "name":
            raise ValueError("Название камеры обязательно")
        return value

    @field_validator("coverage")
    @classmethod
    def normalize_coverage(cls, value: List[str]) -> List[str]:
        return list(dict.fromkeys(item.strip() for item in value if item.strip()))


class PlanItemInput(BaseModel):
    client_id: Optional[str] = None
    id: Optional[str] = None
    stage_code: str = Field(default="", max_length=100)
    name: str = Field(min_length=1, max_length=200)
    note: str = Field(default="", max_length=2000)
    start_date: date
    end_date: date
    confirmation_method: Literal["cameras", "inspection"] = "cameras"
    observability: Literal["yes", "partial", "no"] = "yes"
    camera_ids: List[str] = Field(default_factory=list)
    children: List["PlanItemInput"] = Field(default_factory=list)

    @field_validator("name", "note", "stage_code")
    @classmethod
    def trim_plan_text(cls, value: str, info: ValidationInfo) -> str:
        value = value.strip()
        if not value and info.field_name == "name":
            raise ValueError("Название этапа обязательно")
        return value

    @model_validator(mode="after")
    def validate_interval_and_depth(self):
        if self.start_date > self.end_date:
            raise ValueError("Дата окончания не может быть раньше начала")
        if any(child.children for child in self.children):
            raise ValueError("План допускает не более двух уровней")
        return self


class ScheduleInput(BaseModel):
    effective_from: date = Field(default_factory=date.today)
    times: List[str] = Field(default_factory=lambda: ["09:00", "12:00", "15:00", "18:00"])
    confirmation_threshold: int = Field(default=2, ge=1, le=8)
    absence_threshold: int = Field(default=3, ge=1, le=8)

    @field_validator("times")
    @classmethod
    def validate_times(cls, value: List[str]) -> List[str]:
        if not 1 <= len(value) <= 8:
            raise ValueError("Количество проверок должно быть от 1 до 8")
        if any(not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", item) for item in value):
            raise ValueError("Время должно быть в формате ЧЧ:ММ")
        if len(set(value)) != len(value):
            raise ValueError("Времена проверок не должны повторяться")
        return sorted(value)


class ObjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    object_type: str = Field(default="Жильё", min_length=1, max_length=80)
    address: str = Field(default="", max_length=500)
    timezone: str = Field(default="Europe/Moscow", min_length=1, max_length=80)
    is_draft: bool = False
    cameras: List[CameraInput] = Field(default_factory=list, max_length=16)
    plan_items: List[PlanItemInput] = Field(default_factory=list)
    schedule: ScheduleInput = Field(default_factory=ScheduleInput)

    @field_validator("name", "object_type", "address", "timezone")
    @classmethod
    def trim_object_text(cls, value: str) -> str:
        return value.strip()

    @model_validator(mode="after")
    def validate_required_text_and_timezone(self):
        if not self.name or not self.object_type or not self.timezone:
            raise ValueError("Название, тип объекта и часовой пояс обязательны")
        try:
            ZoneInfo(self.timezone)
        except (ZoneInfoNotFoundError, ValueError):
            raise ValueError("Неизвестный часовой пояс") from None
        return self

    @model_validator(mode="after")
    def validate_ready_object(self):
        names = [item.name.casefold() for item in self.cameras]
        if len(names) != len(set(names)):
            raise ValueError("Названия активных камер должны быть уникальны")
        if not self.is_draft and (not self.cameras or not self.plan_items):
            raise ValueError("Для завершения настройки нужны камера и этап плана")
        return self


class ObjectPatch(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    object_type: Optional[str] = Field(default=None, min_length=1, max_length=80)
    address: Optional[str] = Field(default=None, max_length=500)
    timezone: Optional[str] = Field(default=None, min_length=1, max_length=80)
    is_draft: Optional[bool] = None
    is_archived: Optional[bool] = None

    @field_validator("name", "object_type", "address", "timezone")
    @classmethod
    def trim_optional_text(cls, value: Optional[str]) -> Optional[str]:
        return value.strip() if value is not None else None

    @model_validator(mode="after")
    def validate_optional_required_text(self):
        for field in ("name", "object_type", "timezone"):
            value = getattr(self, field)
            if value is not None and not value:
                raise ValueError("Название, тип объекта и часовой пояс не могут быть пустыми")
        if self.timezone is not None:
            try:
                ZoneInfo(self.timezone)
            except (ZoneInfoNotFoundError, ValueError):
                raise ValueError("Неизвестный часовой пояс") from None
        return self


class CameraResponse(BaseModel):
    id: str
    code: str
    name: str
    zone: str
    sort_order: int
    is_active: bool
    view_description: str
    view_type: str
    placement: str
    orientation: str
    coverage: List[str]
    fov_revision: int


class PlanItemResponse(BaseModel):
    id: str
    parent_id: Optional[str]
    stage_code: str
    name: str
    note: str
    start_date: date
    end_date: date
    confirmation_method: str
    observability: str
    camera_ids: List[str]
    profile_snapshot: Dict[str, Any]
    is_outside_directory: bool
    sort_order: int
    version: int
    children: List["PlanItemResponse"] = Field(default_factory=list)


class ScheduleResponse(BaseModel):
    id: str
    version: int
    effective_from: date
    times: List[str]
    confirmation_threshold: int
    absence_threshold: int
    created_at: datetime


class ObjectDetailResponse(ObjectListItem):
    cameras: List[CameraResponse]
    plan_items: List[PlanItemResponse]
    schedule: ScheduleResponse


class CameraPatch(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=80)
    zone: Optional[str] = Field(default=None, max_length=200)
    sort_order: Optional[int] = Field(default=None, ge=0)
    is_active: Optional[bool] = None
    view_description: Optional[str] = Field(default=None, max_length=1000)
    view_type: Optional[Literal["fixed overview", "fixed detail", "ptz preset"]] = None
    placement: Optional[str] = Field(default=None, max_length=500)
    orientation: Optional[Literal[
        "", "north", "north-east", "east", "south-east", "south", "south-west", "west", "north-west"
    ]] = None
    coverage: Optional[List[str]] = Field(default=None, max_length=50)

    @field_validator("name", "zone", "view_description", "placement")
    @classmethod
    def trim_camera_patch(cls, value: Optional[str], info: ValidationInfo) -> Optional[str]:
        value = value.strip() if value is not None else None
        if value is not None and not value and info.field_name == "name":
            raise ValueError("Название камеры обязательно")
        return value


class PlanGroupRequest(BaseModel):
    item_ids: List[str] = Field(min_length=2)
    name: str = Field(min_length=1, max_length=200)
    confirmation_method: Literal["cameras", "inspection"] = "cameras"

    @field_validator("name")
    @classmethod
    def trim_group_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Название укрупнённого этапа обязательно")
        return value


class PlanItemPatch(BaseModel):
    stage_code: Optional[str] = Field(default=None, max_length=100)
    name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    note: Optional[str] = Field(default=None, max_length=2000)
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    confirmation_method: Optional[Literal["cameras", "inspection"]] = None
    observability: Optional[Literal["yes", "partial", "no"]] = None
    camera_ids: Optional[List[str]] = None
    parent_id: Optional[str] = None
    sort_order: Optional[int] = Field(default=None, ge=0)

    @field_validator("stage_code", "name", "note")
    @classmethod
    def trim_patch_text(cls, value: Optional[str]) -> Optional[str]:
        return value.strip() if value is not None else None


class StageDirectoryItem(BaseModel):
    code: str
    name: str
    section: str = ""
    object_types: List[str]
    observability: str
    confirmation_method: str
    visual_class: str
    note: str = ""
    includes: List[str] = []
    profile: Dict[str, Any]


class SnapshotCreate(BaseModel):
    observed_date: date
    observed_time: str
    source: Literal["manual", "camera"] = "manual"

    @field_validator("observed_time")
    @classmethod
    def validate_observed_time(cls, value: str) -> str:
        if not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", value):
            raise ValueError("Время должно быть в формате ЧЧ:ММ")
        return value


class SnapshotImageResponse(BaseModel):
    id: str
    camera_id: str
    camera_name: str
    camera_zone: str
    original_name: str
    content_type: str
    byte_size: int
    sha256: str
    source: str
    fov_revision: int
    url: str


class AnalysisAttemptResponse(BaseModel):
    id: str
    attempt_number: int
    state: str
    provider: str
    model: str
    prompt_version: str
    request_id: Optional[str]
    duration_ms: Optional[int]
    input_tokens: Optional[int]
    output_tokens: Optional[int]
    estimated_cost: Optional[str]
    raw_response: Optional[Dict[str, Any]]
    normalized_response: Optional[Dict[str, Any]]
    error_code: Optional[str]
    error_detail: Optional[str]
    created_at: datetime
    finished_at: Optional[datetime]


class SnapshotResponse(BaseModel):
    id: str
    object_id: str
    observed_at: datetime
    uploaded_at: datetime
    state: str
    control_slot: Optional[str]
    source: str
    plan_snapshot: Dict[str, Any]
    images: List[SnapshotImageResponse]
    attempts: List[AnalysisAttemptResponse]


class AnalyzeResponse(BaseModel):
    snapshot_id: str
    state: str
    attempt_id: str
    attempt_number: int


class InspectionAttachmentResponse(BaseModel):
    id: str
    original_name: str
    content_type: str
    byte_size: int
    sha256: str
    url: str


class InspectionResponse(BaseModel):
    id: str
    object_id: str
    plan_item_id: str
    observed_date: date
    valid_until: Optional[date]
    verdict: str
    author: str
    role: str
    comment: str
    superseded: bool
    attachments: List[InspectionAttachmentResponse]
    created_at: datetime


class DayEvaluationResponse(BaseModel):
    object_id: str
    date: date
    rules_version: str
    schedule_version: int
    times: List[str]
    received: int
    expected: int
    stages: List[Dict[str, Any]]


class TemporalComparisonCreate(BaseModel):
    first_image_id: str
    second_image_id: str


class TemporalComparisonResponse(BaseModel):
    id: str
    object_id: str
    camera_id: str
    state: str
    provider: str
    model: str
    prompt_version: str
    request_id: Optional[str]
    duration_ms: Optional[int]
    input_tokens: Optional[int]
    output_tokens: Optional[int]
    estimated_cost: Optional[str]
    result: Optional[Dict[str, Any]]
    error_code: Optional[str]
    error_detail: Optional[str]
    first_image: Dict[str, Any]
    second_image: Dict[str, Any]
    created_at: datetime
    finished_at: Optional[datetime]


class MovementSignalsResponse(BaseModel):
    object_id: str
    date: date
    signals: List[Dict[str, Any]]


class WelcomeEmailResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    recipient: EmailStr
    status: str
    attempts: int
    provider_message_id: Optional[str]
    last_error: Optional[str]
    created_at: datetime
    last_attempt_at: Optional[datetime]
    sent_at: Optional[datetime]


class WelcomeEmailListResponse(BaseModel):
    items: List[WelcomeEmailResponse]


class HealthResponse(BaseModel):
    status: str
    database: str
    storage: str
