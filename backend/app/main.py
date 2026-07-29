import json
from contextlib import asynccontextmanager
from pathlib import Path
from uuid import UUID, uuid4

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware

from .config import get_settings
from .database import database
from .schemas import CharacterRequest, PipelineAsset, ProjectCreate, ProjectRef, ProjectResponse, RenderRequest, UploadResponse
from .services.adapters import get_director_adapter
from .services.audio import probe_audio

settings = get_settings()
adapter = get_director_adapter()


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings.media_root.mkdir(parents=True, exist_ok=True)
    database.open()
    yield
    database.close()


app = FastAPI(title=settings.app_name, version="1.0.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "adapter": settings.adapter_mode}


@app.post("/project/create", response_model=ProjectResponse, status_code=201)
def create_project(payload: ProjectCreate) -> ProjectResponse:
    project_id = uuid4()
    with database.connection() as connection:
        connection.execute(
            "INSERT INTO projects(id, name, target_duration) VALUES (%s, %s, %s)",
            (project_id, payload.name, payload.target_duration),
        )
        connection.commit()
    return ProjectResponse(id=project_id, name=payload.name, target_duration=payload.target_duration, status="draft")


@app.post("/audio/upload", response_model=UploadResponse, status_code=201)
async def upload_audio(project_id: UUID = Form(...), audio: UploadFile = File(...)) -> UploadResponse:
    allowed = {"audio/mpeg", "audio/wav", "audio/x-wav", "audio/mp4", "audio/flac"}
    if audio.content_type not in allowed:
        raise HTTPException(status_code=415, detail="Unsupported audio format")
    audio_id = uuid4()
    extension = Path(audio.filename or "audio.bin").suffix.lower()
    target = settings.media_root / str(project_id) / f"{audio_id}{extension}"
    target.parent.mkdir(parents=True, exist_ok=True)
    size = 0
    with target.open("wb") as output:
        while chunk := await audio.read(1024 * 1024):
            size += len(chunk)
            if size > 200 * 1024 * 1024:
                target.unlink(missing_ok=True)
                raise HTTPException(status_code=413, detail="Audio exceeds 200MB")
            output.write(chunk)
    with database.connection() as connection:
        connection.execute(
            """
            INSERT INTO audio_assets(id, project_id, filename, storage_path, content_type, size_bytes)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (audio_id, project_id, audio.filename, str(target), audio.content_type, size),
        )
        connection.commit()
    return UploadResponse(project_id=project_id, audio_id=audio_id, filename=audio.filename or target.name, size=size, status="uploaded")


@app.post("/audio/analyze", response_model=PipelineAsset)
def analyze_audio(payload: ProjectRef) -> PipelineAsset:
    with database.connection() as connection:
        row = connection.execute(
            "SELECT id, storage_path FROM audio_assets WHERE project_id = %s ORDER BY created_at DESC LIMIT 1",
            (payload.project_id,),
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="No audio uploaded for project")
        analysis = probe_audio(Path(row["storage_path"]))
        connection.execute(
            "UPDATE audio_assets SET analysis = %s::jsonb WHERE id = %s",
            (json.dumps(analysis, ensure_ascii=False), row["id"]),
        )
        connection.commit()
    database.insert_asset(payload.project_id, "audio_analysis", analysis)
    return PipelineAsset(project_id=payload.project_id, kind="audio_analysis", payload=analysis)


def create_asset(project_id: UUID, kind: str) -> PipelineAsset:
    context = load_context(project_id)
    result = adapter.generate(kind, context)
    database.insert_asset(project_id, kind, result)
    return PipelineAsset(project_id=project_id, kind=kind, payload=result)


def load_context(project_id: UUID) -> dict:
    with database.connection() as connection:
        project = connection.execute("SELECT * FROM projects WHERE id = %s", (project_id,)).fetchone()
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")
        assets = connection.execute(
            "SELECT kind, payload FROM generated_assets WHERE project_id = %s ORDER BY created_at",
            (project_id,),
        ).fetchall()
    return {"project": dict(project), "assets": {row["kind"]: row["payload"] for row in assets}}


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
    job_id = uuid4()
    job = {
        "aspect_ratio": payload.aspect_ratio,
        "shot_count": len(context["assets"]["shots"]["shots"]),
        "mode": "demo" if settings.adapter_mode == "demo" else "provider",
    }
    with database.connection() as connection:
        connection.execute(
            "INSERT INTO render_jobs(id, project_id, adapter, status, payload) VALUES (%s, %s, %s, %s, %s::jsonb)",
            (job_id, payload.project_id, payload.video_adapter, "queued", json.dumps(job)),
        )
        connection.commit()
    return {"job_id": job_id, "status": "queued", **job}
