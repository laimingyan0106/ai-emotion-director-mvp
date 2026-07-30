from contextlib import asynccontextmanager
from io import BytesIO
from pathlib import Path
from uuid import UUID, uuid4

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from .config import get_settings
from .database import (
    create_project_record,
    create_render_job,
    delete_project_record,
    database,
    get_latest_audio,
    get_project_record,
    list_project_records,
    load_project_context,
    save_audio_analysis,
    save_audio_record,
    update_project_record,
)
from .schemas import (
    CharacterRequest,
    PipelineAsset,
    ProjectCreate,
    ProjectListResponse,
    ProjectRef,
    ProjectResponse,
    ProjectSnapshot,
    ProjectUpdate,
    RenderRequest,
    UploadResponse,
)
from .services.adapters import get_director_adapter
from .services.audio import probe_audio
from .services.storage import get_media_storage

settings = get_settings()
adapter = get_director_adapter()
media_storage = get_media_storage()


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings.resolved_media_root.mkdir(parents=True, exist_ok=True)
    database.open()
    yield
    database.close()


app = FastAPI(title=settings.app_name, version="1.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_origin_regex=settings.cors_origin_regex,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict[str, str | bool]:
    return {
        "status": "ok",
        "adapter": settings.adapter_mode,
        "storage": settings.resolved_storage_mode,
        "durable_storage": settings.resolved_storage_mode == "postgres",
        "media_storage": settings.resolved_media_storage_mode,
    }


@app.post("/project/create", response_model=ProjectResponse, status_code=201)
def create_project(payload: ProjectCreate) -> ProjectResponse:
    project_id = uuid4()
    create_project_record(project_id, payload.name, payload.target_duration)
    return ProjectResponse(id=project_id, name=payload.name, target_duration=payload.target_duration, status="draft")


@app.get("/project/{project_id}", response_model=ProjectSnapshot)
def get_project(project_id: UUID) -> ProjectSnapshot:
    project = get_project_record(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return ProjectSnapshot.model_validate(project)


@app.get("/projects", response_model=ProjectListResponse)
def list_projects() -> ProjectListResponse:
    items = [
        ProjectSnapshot.model_validate(get_project_record(project["id"]) or project)
        for project in list_project_records()
    ]
    return ProjectListResponse(items=items, total=len(items))


@app.get("/projects/{project_id}", response_model=ProjectSnapshot)
def get_project_detail(project_id: UUID) -> ProjectSnapshot:
    return get_project(project_id)


@app.patch("/projects/{project_id}", response_model=ProjectSnapshot)
def update_project(project_id: UUID, payload: ProjectUpdate) -> ProjectSnapshot:
    project = update_project_record(
        project_id,
        name=payload.name,
        target_duration=payload.target_duration,
    )
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return ProjectSnapshot.model_validate(project)


@app.delete("/projects/{project_id}", status_code=204)
async def delete_project(project_id: UUID) -> None:
    storage_paths = delete_project_record(project_id)
    if storage_paths is None:
        raise HTTPException(status_code=404, detail="Project not found")
    for storage_path in storage_paths:
        await media_storage.delete(storage_path)


@app.post("/audio/upload", response_model=UploadResponse, status_code=201)
async def upload_audio(project_id: UUID = Form(...), audio: UploadFile = File(...)) -> UploadResponse:
    allowed = {"audio/mpeg", "audio/wav", "audio/x-wav", "audio/mp4", "audio/flac"}
    if audio.content_type not in allowed:
        raise HTTPException(status_code=415, detail="Unsupported audio format")
    audio_id = uuid4()
    extension = Path(audio.filename or "audio.bin").suffix.lower()
    if not get_project_record(project_id):
        raise HTTPException(status_code=404, detail="Project not found")
    data = await audio.read(200 * 1024 * 1024 + 1)
    size = len(data)
    if size > 200 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Audio exceeds 200MB")
    pathname = f"projects/{project_id}/audio/{audio_id}{extension}"
    storage_path = await media_storage.put(
        pathname,
        BytesIO(data),
        content_type=audio.content_type,
    )
    save_audio_record(audio_id, project_id, audio.filename or f"{audio_id}{extension}", storage_path, audio.content_type, size)
    return UploadResponse(project_id=project_id, audio_id=audio_id, filename=audio.filename or f"{audio_id}{extension}", size=size, status="uploaded")


@app.post("/audio/analyze", response_model=PipelineAsset)
def analyze_audio(payload: ProjectRef) -> PipelineAsset:
    row = get_latest_audio(payload.project_id)
    if not row:
        raise HTTPException(status_code=404, detail="No audio uploaded for project")
    analysis = probe_audio(Path(row["storage_path"]))
    save_audio_analysis(row["id"], analysis)
    database.insert_asset(payload.project_id, "audio_analysis", analysis)
    return PipelineAsset(project_id=payload.project_id, kind="audio_analysis", payload=analysis)


def create_asset(project_id: UUID, kind: str) -> PipelineAsset:
    context = load_context(project_id)
    result = adapter.generate(kind, context)
    database.insert_asset(project_id, kind, result)
    return PipelineAsset(project_id=project_id, kind=kind, payload=result)


def load_context(project_id: UUID) -> dict:
    context = load_project_context(project_id)
    if not context:
        raise HTTPException(status_code=404, detail="Project not found")
    return context


@app.post("/world/create", response_model=PipelineAsset)
def create_world(payload: ProjectRef) -> PipelineAsset:
    return create_asset(payload.project_id, "world")


@app.post("/character/create", response_model=PipelineAsset)
def create_character(payload: CharacterRequest) -> PipelineAsset:
    return create_asset(payload.project_id, "character")


@app.post("/story/create", response_model=PipelineAsset)
def create_story(payload: ProjectRef) -> PipelineAsset:
    return create_asset(payload.project_id, "story")


@app.post("/shots/create", response_model=PipelineAsset)
def create_shots(payload: ProjectRef) -> PipelineAsset:
    return create_asset(payload.project_id, "shots")


@app.post("/render/start", status_code=202)
def start_render(payload: RenderRequest) -> dict:
    context = load_context(payload.project_id)
    if "shots" not in context["assets"]:
        raise HTTPException(status_code=409, detail="Create shots before rendering")
    job = {
        "aspect_ratio": payload.aspect_ratio,
        "shot_count": len(context["assets"]["shots"]["shots"]),
        "mode": "demo" if settings.adapter_mode == "demo" else "provider",
    }
    job_id = create_render_job(payload.project_id, payload.video_adapter, job)
    return {"job_id": job_id, "status": "queued", **job}
