from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field, model_validator


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    target_duration: int = Field(default=30, ge=10, le=180)


class ProjectUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    target_duration: int | None = Field(default=None, ge=10, le=180)


class ProjectRef(BaseModel):
    project_id: UUID


class CharacterRequest(ProjectRef):
    count: int = Field(default=1, ge=1, le=4)


class RenderRequest(ProjectRef):
    video_adapter: str = "demo-video"
    aspect_ratio: Literal["16:9", "9:16", "1:1"] = "16:9"


class PipelineAsset(BaseModel):
    project_id: UUID
    kind: str
    payload: dict[str, Any]
    asset_id: int | None = None
    version: int | None = None
    status: str | None = None
    is_active: bool | None = None


class AssetVersion(BaseModel):
    id: int
    project_id: UUID
    kind: str
    payload: dict[str, Any]
    version: int
    status: Literal["draft", "active", "archived", "failed"]
    is_active: bool
    parent_asset_id: int | None = None
    provider: str | None = None
    model: str | None = None
    prompt: str | None = None
    input_snapshot: dict[str, Any] = Field(default_factory=dict)
    validation_errors: list[Any] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime | None = None


class AssetDependencyWarning(BaseModel):
    asset_id: int
    kind: str
    version: int
    upstream_kind: str
    expected_asset_id: int
    active_asset_id: int
    message: str


class AssetVersionsResponse(BaseModel):
    project_id: UUID
    groups: dict[str, list[AssetVersion]]
    warnings: list[AssetDependencyWarning] = Field(default_factory=list)


class AssetActivateRequest(BaseModel):
    asset_id: int | None = Field(default=None, ge=1)
    version: int | None = Field(default=None, ge=1)

    @model_validator(mode="after")
    def require_exactly_one_selector(self) -> "AssetActivateRequest":
        if (self.asset_id is None) == (self.version is None):
            raise ValueError("Provide exactly one of asset_id or version")
        return self


class AssetActivationResponse(BaseModel):
    asset: AssetVersion
    warnings: list[AssetDependencyWarning] = Field(default_factory=list)


class SegmentCandidate(BaseModel):
    category: Literal["highlight", "turn", "stable"]
    label: str
    start: float
    end: float
    duration: float
    score: float
    reason: str


class SegmentRecommendationsResponse(BaseModel):
    project_id: UUID
    target_duration: float
    audio_duration: float
    candidates: list[SegmentCandidate]


class SegmentConfirmRequest(BaseModel):
    start: float = Field(ge=0)
    end: float = Field(gt=0)
    category: Literal["highlight", "turn", "stable", "custom"] = "custom"
    label: str = Field(default="自定义片段", min_length=1, max_length=80)


class SegmentConfirmationResponse(BaseModel):
    asset: AssetVersion
    warnings: list[AssetDependencyWarning] = Field(default_factory=list)


class ProjectResponse(BaseModel):
    id: UUID
    name: str
    target_duration: int
    status: str
    created_at: datetime | None = None
    updated_at: datetime | None = None


class UploadResponse(BaseModel):
    project_id: UUID
    audio_id: UUID
    filename: str
    size: int
    status: str


class AudioSummary(BaseModel):
    id: UUID
    filename: str
    content_type: str | None = None
    size_bytes: int


class ProjectSnapshot(ProjectResponse):
    audio: AudioSummary | None = None


class ProjectListResponse(BaseModel):
    items: list[ProjectSnapshot]
    total: int
