import asyncio
from contextlib import asynccontextmanager
from copy import deepcopy
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
import tempfile
from uuid import UUID, uuid4

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response

from .config import get_settings
from .domain import CharacterAsset
from .database import (
    create_project_record,
    create_render_job,
    delete_project_record,
    activate_asset_version,
    database,
    get_active_asset_snapshot,
    get_asset_dependency_warnings,
    get_latest_audio,
    get_project_record,
    insert_asset_version,
    list_asset_versions,
    list_project_records,
    load_project_context,
    save_audio_analysis,
    save_audio_record,
    update_project_record,
)
from .schemas import (
    AssetActivateRequest,
    AssetActivationResponse,
    AssetVersion,
    AssetVersionsResponse,
    CharacterReferenceGenerateRequest,
    CharacterReferenceResponse,
    CharacterReferenceSelectionRequest,
    CharacterRequest,
    PipelineAsset,
    ProjectCreate,
    ProjectListResponse,
    ProjectRef,
    ProjectResponse,
    ProjectSnapshot,
    ProjectUpdate,
    RenderRequest,
    SegmentConfirmRequest,
    SegmentConfirmationResponse,
    SegmentRecommendationsResponse,
    UploadResponse,
    WorldUpdateRequest,
    WorldUpdateResponse,
)
from .services.adapters import get_director_adapter
from .services.audio import analyze_audio_file, demo_analysis
from .services.character_references import get_character_image_adapter
from .services.generation import AssetGenerationError, generate_validated_asset
from .services.providers import ProviderRequestError
from .services.segments import (
    SegmentSelectionError,
    recommend_segments,
    restrict_context_to_confirmed_segment,
    validate_confirmed_segment,
)
from .services.storage import get_media_storage
from .services.world import (
    WorldEditError,
    edit_world,
    preserve_locked_world_fields,
)

settings = get_settings()
adapter = get_director_adapter()
media_storage = get_media_storage()
character_image_adapter = get_character_image_adapter()


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
def health() -> dict[str, str | bool | None]:
    return {
        "status": "ok",
        "adapter": adapter.provider_name,
        "adapter_configured": settings.adapter_mode,
        "adapter_fallback_reason": adapter.fallback_reason,
        "director_model": adapter.model_name,
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
async def analyze_audio(payload: ProjectRef) -> PipelineAsset:
    row = get_latest_audio(payload.project_id)
    if not row:
        raise HTTPException(status_code=404, detail="No audio uploaded for project")
    analysis = row.get("analysis")
    active_analysis = next(
        (
            asset
            for asset in list_asset_versions(payload.project_id, "audio_analysis")
            if asset["is_active"]
        ),
        None,
    )
    if analysis and active_analysis and active_analysis["payload"] == analysis:
        return PipelineAsset(
            project_id=payload.project_id,
            kind="audio_analysis",
            payload=analysis,
            asset_id=active_analysis["id"],
            version=active_analysis["version"],
            status=active_analysis["status"],
            is_active=active_analysis["is_active"],
        )
    if analysis is None:
        try:
            audio_bytes = await media_storage.read(str(row["storage_path"]))
            with tempfile.TemporaryDirectory(prefix="emotion-director-analysis-") as directory:
                suffix = Path(str(row.get("filename") or "audio.bin")).suffix or ".bin"
                analysis_path = Path(directory) / f"source{suffix}"
                analysis_path.write_bytes(audio_bytes)
                analysis = await asyncio.wait_for(
                    asyncio.to_thread(
                        analyze_audio_file,
                        analysis_path,
                        max_duration_seconds=settings.audio_analysis_max_seconds,
                        decode_timeout_seconds=min(
                            settings.audio_analysis_timeout_seconds,
                            30,
                        ),
                    ),
                    timeout=settings.audio_analysis_timeout_seconds,
                )
        except TimeoutError:
            analysis = demo_analysis(
                degraded=True,
                reason=(
                    "analysis_timeout_"
                    f"{settings.audio_analysis_timeout_seconds}s"
                ),
            )
        except Exception as error:
            analysis = demo_analysis(
                degraded=True,
                reason=f"media_read_or_analysis_failed:{error}",
            )
    save_audio_analysis(row["id"], analysis)
    asset = insert_asset_version(
        payload.project_id,
        "audio_analysis",
        analysis,
        activate=True,
        provider="local",
        model=str(analysis.get("analysis_version", "audio-analysis")),
        input_snapshot={
            "audio": {
                "audio_id": str(row["id"]),
                "source_sha256": analysis.get("source_sha256"),
            }
        },
    )
    return PipelineAsset(
        project_id=payload.project_id,
        kind="audio_analysis",
        payload=analysis,
        asset_id=asset["id"],
        version=asset["version"],
        status=asset["status"],
        is_active=asset["is_active"],
    )


def create_asset(project_id: UUID, kind: str) -> PipelineAsset:
    context = load_context(project_id)
    try:
        context = restrict_context_to_confirmed_segment(context)
    except SegmentSelectionError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    current_same_kind = context.get("assets", {}).get(kind)
    if (
        kind == "character"
        and isinstance(current_same_kind, dict)
        and current_same_kind.get("locked")
    ):
        raise HTTPException(
            status_code=409,
            detail="Unlock the active Character Asset before regenerating it",
        )
    input_snapshot = generation_input_snapshot(project_id, kind)
    prompt = adapter.build_prompt(kind, context)
    try:
        generation = generate_validated_asset(
            adapter,
            kind,
            context,
            retry_attempts=settings.generation_retry_attempts,
        )
    except AssetGenerationError as error:
        insert_asset_version(
            project_id,
            kind,
            error.last_payload,
            activate=False,
            provider=adapter.provider_name,
            model=adapter.model_name,
            prompt=prompt,
            input_snapshot=input_snapshot,
            validation_errors=error.validation_errors,
        )
        raise HTTPException(
            status_code=422,
            detail={
                "message": str(error),
                "validation_errors": error.validation_errors,
            },
        ) from error
    except ProviderRequestError as error:
        validation_errors = [
            {
                "attempt": 1,
                "location": [],
                "type": error.__class__.__name__,
                "message": str(error),
                "status_code": error.status_code,
                "retryable": error.retryable,
            }
        ]
        insert_asset_version(
            project_id,
            kind,
            {},
            activate=False,
            provider=adapter.provider_name,
            model=adapter.model_name,
            prompt=prompt,
            input_snapshot=input_snapshot,
            validation_errors=validation_errors,
        )
        raise HTTPException(
            status_code=502,
            detail={
                "message": "Director provider request failed",
                "provider": adapter.provider_name,
                "model": adapter.model_name,
                "errors": validation_errors,
            },
        ) from error
    result = generation.model.model_dump(mode="json")
    if kind == "world" and isinstance(current_same_kind, dict):
        result = preserve_locked_world_fields(
            current_same_kind,
            result,
        ).model_dump(mode="json")
    asset = insert_asset_version(
        project_id,
        kind,
        result,
        activate=True,
        provider=adapter.provider_name,
        model=adapter.model_name,
        prompt=prompt,
        input_snapshot=input_snapshot,
        validation_errors=generation.validation_errors,
    )
    return PipelineAsset(
        project_id=project_id,
        kind=kind,
        payload=result,
        asset_id=asset["id"],
        version=asset["version"],
        status=asset["status"],
        is_active=asset["is_active"],
    )


def load_context(project_id: UUID) -> dict:
    context = load_project_context(project_id)
    if not context:
        raise HTTPException(status_code=404, detail="Project not found")
    return context


def generation_input_snapshot(
    project_id: UUID,
    kind: str,
) -> dict[str, dict[str, int]]:
    dependencies = {
        "world": {"audio_analysis", "segment"},
        "character": {"audio_analysis", "segment", "world"},
        "story": {"audio_analysis", "segment", "world", "character"},
        "shots": {"audio_analysis", "segment", "world", "character", "story"},
    }
    snapshot = get_active_asset_snapshot(project_id, exclude_kind=kind)
    return {
        asset_kind: reference
        for asset_kind, reference in snapshot.items()
        if asset_kind in dependencies.get(kind, set())
    }


@app.get("/projects/{project_id}/assets", response_model=AssetVersionsResponse)
def get_project_assets(project_id: UUID) -> AssetVersionsResponse:
    if not get_project_record(project_id):
        raise HTTPException(status_code=404, detail="Project not found")
    groups: dict[str, list[AssetVersion]] = {}
    for asset in list_asset_versions(project_id):
        groups.setdefault(asset["kind"], []).append(AssetVersion.model_validate(asset))
    return AssetVersionsResponse(
        project_id=project_id,
        groups=groups,
        warnings=get_asset_dependency_warnings(project_id),
    )


@app.post(
    "/projects/{project_id}/assets/{kind}/activate",
    response_model=AssetActivationResponse,
)
def activate_project_asset(
    project_id: UUID,
    kind: str,
    payload: AssetActivateRequest,
) -> AssetActivationResponse:
    try:
        asset = activate_asset_version(
            project_id,
            kind,
            asset_id=payload.asset_id,
            version=payload.version,
        )
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    if not asset:
        raise HTTPException(status_code=404, detail="Asset version not found")
    return AssetActivationResponse(
        asset=AssetVersion.model_validate(asset),
        warnings=get_asset_dependency_warnings(project_id),
    )


@app.get(
    "/projects/{project_id}/segments/recommendations",
    response_model=SegmentRecommendationsResponse,
)
def get_segment_recommendations(
    project_id: UUID,
) -> SegmentRecommendationsResponse:
    project = get_project_record(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    analysis_asset = next(
        (
            asset
            for asset in list_asset_versions(project_id, "audio_analysis")
            if asset["is_active"]
        ),
        None,
    )
    if not analysis_asset:
        raise HTTPException(
            status_code=409,
            detail="Analyze audio before selecting a segment",
        )
    analysis = analysis_asset["payload"]
    try:
        candidates = recommend_segments(
            analysis,
            target_duration=float(project["target_duration"]),
        )
    except SegmentSelectionError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    return SegmentRecommendationsResponse(
        project_id=project_id,
        target_duration=float(project["target_duration"]),
        audio_duration=float(analysis["duration"]),
        candidates=candidates,
    )


@app.post(
    "/projects/{project_id}/segments/confirm",
    response_model=SegmentConfirmationResponse,
)
def confirm_project_segment(
    project_id: UUID,
    payload: SegmentConfirmRequest,
) -> SegmentConfirmationResponse:
    project = get_project_record(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    audio = get_latest_audio(project_id)
    analysis_asset = next(
        (
            asset
            for asset in list_asset_versions(project_id, "audio_analysis")
            if asset["is_active"]
        ),
        None,
    )
    if not audio or not analysis_asset:
        raise HTTPException(
            status_code=409,
            detail="Analyze audio before selecting a segment",
        )
    try:
        segment = validate_confirmed_segment(
            start=payload.start,
            end=payload.end,
            category=payload.category,
            label=payload.label,
            target_duration=float(project["target_duration"]),
            audio_duration=float(analysis_asset["payload"]["duration"]),
            audio_id=str(audio["id"]),
            audio_analysis_asset_id=int(analysis_asset["id"]),
        )
    except SegmentSelectionError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    snapshot = get_active_asset_snapshot(project_id, exclude_kind="segment")
    asset = insert_asset_version(
        project_id,
        "segment",
        segment.model_dump(mode="json"),
        activate=True,
        provider="user",
        model="manual-confirmation",
        input_snapshot={"audio_analysis": snapshot["audio_analysis"]},
    )
    return SegmentConfirmationResponse(
        asset=AssetVersion.model_validate(asset),
        warnings=get_asset_dependency_warnings(project_id),
    )


@app.patch(
    "/projects/{project_id}/world",
    response_model=WorldUpdateResponse,
)
def update_project_world(
    project_id: UUID,
    payload: WorldUpdateRequest,
) -> WorldUpdateResponse:
    current = next(
        (
            asset
            for asset in list_asset_versions(project_id, "world")
            if asset["is_active"]
        ),
        None,
    )
    if not current:
        raise HTTPException(status_code=404, detail="Active World not found")
    if int(current["version"]) != payload.expected_version:
        raise HTTPException(
            status_code=409,
            detail={
                "message": "World version conflict",
                "expected_version": payload.expected_version,
                "active_version": current["version"],
            },
        )
    try:
        edited = edit_world(
            current["payload"],
            changes=payload.changes,
            locked_fields=payload.locked_fields,
        )
    except (WorldEditError, ValueError) as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    asset = insert_asset_version(
        project_id,
        "world",
        edited.model_dump(mode="json"),
        activate=True,
        provider="user",
        model="world-studio",
        prompt="Manual structured World Studio edit",
        input_snapshot=generation_input_snapshot(project_id, "world"),
    )
    return WorldUpdateResponse(
        asset=AssetVersion.model_validate(asset),
        warnings=get_asset_dependency_warnings(project_id),
    )


@app.post("/world/create", response_model=PipelineAsset)
def create_world(payload: ProjectRef) -> PipelineAsset:
    return create_asset(payload.project_id, "world")


@app.post("/character/create", response_model=PipelineAsset)
def create_character(payload: CharacterRequest) -> PipelineAsset:
    return create_asset(payload.project_id, "character")


def _active_character_asset(project_id: UUID) -> dict:
    current = next(
        (
            asset
            for asset in list_asset_versions(project_id, "character")
            if asset["is_active"]
        ),
        None,
    )
    if not current:
        raise HTTPException(status_code=404, detail="Active Character Asset not found")
    return current


def _assert_character_version(current: dict, expected_version: int) -> None:
    if int(current["version"]) != expected_version:
        raise HTTPException(
            status_code=409,
            detail={
                "message": "Character version conflict",
                "expected_version": expected_version,
                "active_version": current["version"],
            },
        )


def _character_consistency_risk(payload: dict) -> str | None:
    selected = [
        item
        for item in payload.get("reference_images", [])
        if item.get("selected")
    ]
    framings = {item.get("framing") for item in selected}
    if framings != {"portrait", "half", "full"}:
        return (
            "角色尚未确认 portrait、half、full 三类参考图；仅凭文本无法承诺"
            "跨镜头人物一致性。"
        )
    if not payload.get("locked"):
        return "参考图已选择但角色资产尚未锁定，后续版本替换可能导致人物漂移。"
    return None


@app.post(
    "/projects/{project_id}/characters/references/generate",
    response_model=CharacterReferenceResponse,
)
async def generate_character_references(
    project_id: UUID,
    request: CharacterReferenceGenerateRequest,
) -> CharacterReferenceResponse:
    current = _active_character_asset(project_id)
    _assert_character_version(current, request.expected_version)
    if current["payload"].get("locked"):
        raise HTTPException(
            status_code=409,
            detail="Unlock the Character Asset before generating new candidates",
        )
    updated = deepcopy(current["payload"])
    if len(updated.get("reference_images", [])) + 3 > 24:
        raise HTTPException(
            status_code=409,
            detail="Character reference candidate limit reached",
        )
    generated_references: list[dict] = []
    uploaded_paths: list[str] = []
    try:
        for framing in ("portrait", "half", "full"):
            reference_id = f"REF-{framing.upper()}-{uuid4().hex[:8].upper()}"
            generated = await character_image_adapter.generate(updated, framing)
            suffix = {
                "image/svg+xml": "svg",
                "image/png": "png",
                "image/jpeg": "jpg",
                "image/webp": "webp",
            }[generated.content_type]
            storage_path = await media_storage.put(
                (
                    f"projects/{project_id}/characters/{updated['id']}/"
                    f"{reference_id}.{suffix}"
                ),
                BytesIO(generated.content),
                content_type=generated.content_type,
            )
            uploaded_paths.append(storage_path)
            generated_references.append(
                {
                    "id": reference_id,
                    "framing": framing,
                    "storage_path": storage_path,
                    "content_type": generated.content_type,
                    "provider": generated.provider,
                    "model": generated.model,
                    "selected": False,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                }
            )
    except Exception as error:
        for storage_path in uploaded_paths:
            try:
                await media_storage.delete(storage_path)
            except Exception:
                pass
        raise HTTPException(
            status_code=502,
            detail=f"Character reference provider failed: {error}",
        ) from error
    updated["reference_images"] = [
        *updated.get("reference_images", []),
        *generated_references,
    ]
    updated["provider_bindings"] = {
        **updated.get("provider_bindings", {}),
        "reference_provider": generated_references[0]["provider"],
        "reference_model": generated_references[0]["model"],
    }
    updated = CharacterAsset.model_validate(updated).model_dump(mode="json")
    asset = insert_asset_version(
        project_id,
        "character",
        updated,
        activate=True,
        provider=generated_references[0]["provider"],
        model=generated_references[0]["model"],
        prompt="Generate portrait, half, and full character reference candidates",
        input_snapshot=generation_input_snapshot(project_id, "character"),
    )
    return CharacterReferenceResponse(
        asset=AssetVersion.model_validate(asset),
        warnings=get_asset_dependency_warnings(project_id),
        consistency_risk=_character_consistency_risk(updated),
    )


@app.patch(
    "/projects/{project_id}/characters/references",
    response_model=CharacterReferenceResponse,
)
def select_character_references(
    project_id: UUID,
    request: CharacterReferenceSelectionRequest,
) -> CharacterReferenceResponse:
    current = _active_character_asset(project_id)
    _assert_character_version(current, request.expected_version)
    updated = deepcopy(current["payload"])
    candidates = updated.get("reference_images", [])
    known_ids = {item["id"] for item in candidates}
    selected_ids = list(dict.fromkeys(request.selected_reference_ids))
    unknown = sorted(set(selected_ids) - known_ids)
    if unknown:
        raise HTTPException(
            status_code=422,
            detail=f"Unknown character reference ids: {', '.join(unknown)}",
        )
    for item in candidates:
        item["selected"] = item["id"] in selected_ids
    selected_counts = {
        framing: sum(
            1
            for item in candidates
            if item.get("selected") and item["framing"] == framing
        )
        for framing in ("portrait", "half", "full")
    }
    if request.locked and any(count != 1 for count in selected_counts.values()):
        raise HTTPException(
            status_code=422,
            detail="Locking requires one selected portrait, half, and full reference",
        )
    updated["locked"] = request.locked
    updated["provider_bindings"] = {
        **updated.get("provider_bindings", {}),
        "selected_reference_ids": ",".join(selected_ids),
    }
    updated = CharacterAsset.model_validate(updated).model_dump(mode="json")
    asset = insert_asset_version(
        project_id,
        "character",
        updated,
        activate=True,
        provider="user",
        model="character-reference-lock",
        prompt="Select and lock character reference candidates",
        input_snapshot=generation_input_snapshot(project_id, "character"),
    )
    return CharacterReferenceResponse(
        asset=AssetVersion.model_validate(asset),
        warnings=get_asset_dependency_warnings(project_id),
        consistency_risk=_character_consistency_risk(updated),
    )


@app.get(
    "/projects/{project_id}/character-assets/{asset_id}/references/{reference_id}",
)
async def get_character_reference(
    project_id: UUID,
    asset_id: int,
    reference_id: str,
    download: bool = False,
) -> Response:
    asset = next(
        (
            item
            for item in list_asset_versions(project_id, "character")
            if int(item["id"]) == asset_id
        ),
        None,
    )
    if not asset:
        raise HTTPException(status_code=404, detail="Character Asset not found")
    reference = next(
        (
            item
            for item in asset["payload"].get("reference_images", [])
            if item.get("id") == reference_id
        ),
        None,
    )
    if not reference:
        raise HTTPException(status_code=404, detail="Character reference not found")
    try:
        content = await media_storage.read(reference["storage_path"])
    except Exception as error:
        raise HTTPException(
            status_code=502,
            detail=f"Character reference media unavailable: {error}",
        ) from error
    extension = {
        "image/svg+xml": "svg",
        "image/png": "png",
        "image/jpeg": "jpg",
        "image/webp": "webp",
    }[reference["content_type"]]
    disposition = "attachment" if download else "inline"
    return Response(
        content=content,
        media_type=reference["content_type"],
        headers={
            "Content-Disposition": (
                f'{disposition}; filename="{reference_id}.{extension}"'
            ),
            "X-Content-Type-Options": "nosniff",
        },
    )


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
