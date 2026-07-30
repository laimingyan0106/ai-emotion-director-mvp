from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field


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
