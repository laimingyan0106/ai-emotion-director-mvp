import os
import tempfile
import unittest
import wave
import math
import json
import struct
import zipfile
from copy import deepcopy
from io import BytesIO
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from uuid import UUID
from uuid import uuid4

from fastapi.testclient import TestClient


TEST_ROOT = Path(tempfile.mkdtemp(prefix="emotion-director-api-"))
os.environ["STORAGE_MODE"] = "sqlite"
os.environ["SQLITE_PATH"] = str(TEST_ROOT / "test.db")
os.environ["MEDIA_ROOT"] = str(TEST_ROOT / "media")

from app.main import app  # noqa: E402
import app.main as main_module  # noqa: E402
from app.database import (  # noqa: E402
    count_project_dependents,
    insert_asset_version,
    list_asset_versions,
    load_project_context,
    save_audio_record,
)
from app.services.adapters import DemoDirectorAdapter, DirectorAdapter  # noqa: E402
from app.services.audio import demo_analysis  # noqa: E402
from app.services.character_references import (  # noqa: E402
    CharacterImageAdapter,
    GeneratedCharacterReference,
)
from app.services.keyframes import DemoKeyframeImageAdapter  # noqa: E402
from app.services.segments import restrict_context_to_confirmed_segment  # noqa: E402
from app.services.providers import ProviderRequestError  # noqa: E402


class AlwaysMalformedAdapter(DirectorAdapter):
    def generate(self, task, context):
        return '{"wrong": true}'


class FailingProviderAdapter(DirectorAdapter):
    provider_name = "mock-provider"
    model_name = "mock-model"

    def generate(self, task, context):
        raise ProviderRequestError(
            "mock rate limit exhausted",
            status_code=429,
            retryable=True,
        )


class ChangingWorldAdapter(DirectorAdapter):
    provider_name = "mock-provider"
    model_name = "mock-world-model"

    def generate(self, task, context):
        payload = DemoDirectorAdapter().generate(task, context)
        if task == "world":
            payload["name"] = "重新生成的世界"
            payload["mutable_state"]["weather"] = "晴朗无雨"
        return payload


class RecordingImageAdapter(CharacterImageAdapter):
    def __init__(self):
        self.calls = []

    async def generate(self, character, framing):
        self.calls.append((character["id"], framing))
        return GeneratedCharacterReference(
            content=f"<svg><title>{framing}</title></svg>".encode(),
            content_type="image/svg+xml",
            provider="mock-image",
            model="mock-reference-v1",
        )


class CountingShotAdapter(DemoDirectorAdapter):
    provider_name = "mock-shot"
    model_name = "mock-shot-v1"

    def __init__(self):
        super().__init__()
        self.group_calls = 0
        self.single_calls = []

    def generate(self, task, context):
        if task == "shots":
            self.group_calls += 1
        return super().generate(task, context)

    def regenerate_shot(self, current_shot, context):
        self.single_calls.append(current_shot["id"])
        result = deepcopy(current_shot)
        result["action"] = f"{current_shot['action']} · 局部再生成"
        result["prompt"] = f"{current_shot['prompt']} · regenerated only"
        return result


def sine_wav_bytes(duration: float = 1.0, sample_rate: int = 22050) -> bytes:
    buffer = BytesIO()
    with wave.open(buffer, "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(sample_rate)
        frames = [
            struct.pack(
                "<h",
                int(32767 * 0.35 * math.sin(2 * math.pi * 440 * index / sample_rate)),
            )
            for index in range(round(duration * sample_rate))
        ]
        output.writeframes(b"".join(frames))
    return buffer.getvalue()


def seed_confirmed_segment(project_id: str, duration: float = 60.0):
    project_uuid = UUID(project_id)
    audio_id = uuid4()
    save_audio_record(
        audio_id,
        project_uuid,
        "seed.wav",
        str(TEST_ROOT / "media" / "seed.wav"),
        "audio/wav",
        1,
    )
    analysis = demo_analysis()
    analysis["duration"] = duration
    analysis["energy_curve"] = [
        round((math.sin(index / 8) + 1) / 2, 4)
        for index in range(100)
    ]
    analysis["emotion_curve"] = [
        round(value * 100)
        for value in analysis["energy_curve"]
    ]
    analysis_asset = insert_asset_version(
        project_uuid,
        "audio_analysis",
        analysis,
        activate=True,
        provider="test",
        model="fixture",
    )
    segment = insert_asset_version(
        project_uuid,
        "segment",
        {
            "start": 0,
            "end": 30,
            "duration": 30,
            "category": "custom",
            "label": "测试片段",
            "confirmed": True,
            "audio_id": str(audio_id),
            "audio_analysis_asset_id": analysis_asset["id"],
        },
        activate=True,
        provider="test",
        model="fixture",
        input_snapshot={
            "audio_analysis": {
                "asset_id": analysis_asset["id"],
                "version": analysis_asset["version"],
            }
        },
    )
    return analysis_asset, segment


class ApiIntegrationTest(unittest.TestCase):
    def test_keyframe_queue_partial_retry_confirmation_and_download_package(self):
        original_adapter = main_module.keyframe_image_adapter
        try:
            with TestClient(app) as client:
                project_id = client.post(
                    "/project/create",
                    json={"name": "Keyframe queue"},
                ).json()["id"]
                seed_confirmed_segment(project_id)
                client.post("/world/create", json={"project_id": project_id})
                client.post("/character/create", json={"project_id": project_id})
                client.post("/story/create", json={"project_id": project_id})
                shots = client.post(
                    "/shots/create",
                    json={"project_id": project_id},
                ).json()

                main_module.keyframe_image_adapter = DemoKeyframeImageAdapter(
                    {"S04"}
                )
                started = client.post(
                    f"/projects/{project_id}/keyframes/start",
                    json={"expected_shots_version": shots["version"]},
                )
                self.assertEqual(started.status_code, 200)
                first = started.json()
                self.assertEqual(first["progress"]["total"], 10)
                self.assertEqual(first["progress"]["succeeded"], 9)
                self.assertEqual(first["progress"]["failed"], 1)
                failed = next(
                    task
                    for task in first["asset"]["payload"]["tasks"]
                    if task["shot_id"] == "S04"
                )
                self.assertEqual(failed["status"], "failed")
                self.assertTrue(failed["provider_task_id"])
                self.assertTrue(failed["error"])
                self.assertTrue(
                    any("S04" in warning for warning in first["consistency_warnings"])
                )

                main_module.keyframe_image_adapter = DemoKeyframeImageAdapter()
                retried = client.post(
                    f"/projects/{project_id}/keyframes/S04/retry",
                    json={"expected_version": first["asset"]["version"]},
                )
                self.assertEqual(retried.status_code, 200)
                second = retried.json()
                self.assertEqual(second["progress"]["succeeded"], 10)
                retried_task = next(
                    task
                    for task in second["asset"]["payload"]["tasks"]
                    if task["shot_id"] == "S04"
                )
                self.assertEqual(retried_task["attempt"], 2)

                s01_before = next(
                    task
                    for task in second["asset"]["payload"]["tasks"]
                    if task["shot_id"] == "S01"
                )
                confirmed = client.patch(
                    f"/projects/{project_id}/keyframes/S01",
                    json={
                        "expected_version": second["asset"]["version"],
                        "confirmed": True,
                    },
                )
                self.assertEqual(confirmed.status_code, 200)
                third = confirmed.json()
                self.assertEqual(third["progress"]["confirmed"], 1)
                rejected_retry = client.post(
                    f"/projects/{project_id}/keyframes/S01/retry",
                    json={"expected_version": third["asset"]["version"]},
                )
                self.assertEqual(rejected_retry.status_code, 409)

                regrouped = client.post(
                    f"/projects/{project_id}/keyframes/start",
                    json={"expected_shots_version": shots["version"]},
                )
                self.assertEqual(regrouped.status_code, 200)
                self.assertEqual(regrouped.json()["progress"]["succeeded"], 10)
                self.assertEqual(regrouped.json()["progress"]["failed"], 0)
                s01_after = next(
                    task
                    for task in regrouped.json()["asset"]["payload"]["tasks"]
                    if task["shot_id"] == "S01"
                )
                self.assertTrue(s01_after["confirmed"])
                self.assertEqual(
                    s01_after["provider_task_id"],
                    s01_before["provider_task_id"],
                )
                self.assertTrue(
                    all(
                        task["attempt"]
                        == (
                            1
                            if task["shot_id"] == "S01"
                            else 3
                            if task["shot_id"] == "S04"
                            else 2
                        )
                        for task in regrouped.json()["asset"]["payload"]["tasks"]
                    )
                )

                image = client.get(
                    f"/projects/{project_id}/keyframes/S04/image"
                )
                self.assertEqual(image.status_code, 200)
                self.assertEqual(image.headers["content-type"], "image/svg+xml")
                self.assertTrue(image.content.startswith(b"<svg"))

                manifest_json = client.get(
                    f"/projects/{project_id}/keyframes/manifest.json"
                )
                self.assertEqual(manifest_json.status_code, 200)
                manifest = manifest_json.json()
                self.assertEqual(len(manifest["tasks"]), 10)
                self.assertEqual(manifest["progress"]["succeeded"], 10)
                manifest_pdf = client.get(
                    f"/projects/{project_id}/keyframes/manifest.pdf"
                )
                self.assertEqual(manifest_pdf.status_code, 200)
                self.assertTrue(manifest_pdf.content.startswith(b"%PDF-1.4"))

                package = client.get(
                    f"/projects/{project_id}/keyframes/export.zip"
                )
                self.assertEqual(package.status_code, 200)
                with zipfile.ZipFile(BytesIO(package.content)) as archive:
                    names = set(archive.namelist())
                    self.assertIn("manifest.json", names)
                    self.assertIn("manifest.pdf", names)
                    self.assertEqual(
                        len(
                            [
                                name
                                for name in names
                                if name.startswith("keyframes/")
                            ]
                        ),
                        10,
                    )
                    zipped_manifest = json.loads(
                        archive.read("manifest.json").decode("utf-8")
                    )
                    self.assertEqual(zipped_manifest["tasks"], manifest["tasks"])
        finally:
            main_module.keyframe_image_adapter = original_adapter

    def test_shot_editor_reorder_versioning_local_regenerate_and_lock(self):
        with TestClient(app) as client:
            project_id = client.post(
                "/project/create",
                json={"name": "Shot editor"},
            ).json()["id"]
            seed_confirmed_segment(project_id)
            client.post("/world/create", json={"project_id": project_id})
            client.post("/character/create", json={"project_id": project_id})
            client.post("/story/create", json={"project_id": project_id})
            created = client.post(
                "/shots/create",
                json={"project_id": project_id},
            )
            self.assertEqual(created.status_code, 200)
            original = created.json()
            edited_shots = deepcopy(original["payload"]["shots"])
            moved = edited_shots.pop(1)
            edited_shots.insert(0, moved)
            edited_shots[1]["action"] = "这是被用户锁定的动作"
            edited_shots[1]["locked"] = True
            edited_shots.pop()
            duplicate = deepcopy(edited_shots[-1])
            duplicate["id"] = "S11"
            duplicate["locked"] = False
            duplicate["action"] = "复制新增镜头"
            edited_shots.append(duplicate)

            edited = client.patch(
                f"/projects/{project_id}/shots",
                json={
                    "expected_version": original["version"],
                    "shots": edited_shots,
                },
            )
            self.assertEqual(edited.status_code, 200)
            edited_asset = edited.json()["asset"]
            self.assertEqual(edited_asset["version"], original["version"] + 1)
            self.assertEqual(
                [shot["id"] for shot in edited_asset["payload"]["shots"][:2]],
                ["S02", "S01"],
            )
            self.assertEqual(
                [shot["start_ms"] for shot in edited_asset["payload"]["shots"][:3]],
                [0, 3000, 6000],
            )
            self.assertIn(
                "S11",
                [shot["id"] for shot in edited_asset["payload"]["shots"]],
            )
            self.assertNotIn(
                "S10",
                [shot["id"] for shot in edited_asset["payload"]["shots"]],
            )

            invalid = deepcopy(edited_asset["payload"]["shots"])
            invalid[0]["duration"] = 2
            rejected = client.patch(
                f"/projects/{project_id}/shots",
                json={
                    "expected_version": edited_asset["version"],
                    "shots": invalid,
                },
            )
            self.assertEqual(rejected.status_code, 422)
            active_after_rejection = next(
                item
                for item in list_asset_versions(UUID(project_id), "shots")
                if item["is_active"]
            )
            self.assertEqual(active_after_rejection["id"], edited_asset["id"])

            mock_adapter = CountingShotAdapter()
            original_adapter = main_module.adapter
            main_module.adapter = mock_adapter
            try:
                local = client.post(
                    f"/projects/{project_id}/shots/S02/regenerate",
                    json={"expected_version": edited_asset["version"]},
                )
                self.assertEqual(local.status_code, 200)
                local_asset = local.json()["asset"]
                self.assertEqual(mock_adapter.single_calls, ["S02"])
                self.assertEqual(mock_adapter.group_calls, 0)
                changed = [
                    shot["id"]
                    for before, shot in zip(
                        edited_asset["payload"]["shots"],
                        local_asset["payload"]["shots"],
                    )
                    if before != shot
                ]
                self.assertEqual(changed, ["S02"])

                blocked = client.post(
                    f"/projects/{project_id}/shots/S01/regenerate",
                    json={"expected_version": local_asset["version"]},
                )
                self.assertEqual(blocked.status_code, 409)

                bulk = client.post(
                    "/shots/create",
                    json={"project_id": project_id},
                )
            finally:
                main_module.adapter = original_adapter
            self.assertEqual(bulk.status_code, 200)
            locked_shot = next(
                shot
                for shot in bulk.json()["payload"]["shots"]
                if shot["id"] == "S01"
            )
            self.assertEqual(locked_shot["action"], "这是被用户锁定的动作")
            self.assertTrue(locked_shot["locked"])

    def test_character_references_lock_download_and_shot_version_integrity(self):
        with TestClient(app) as client:
            project_id = client.post(
                "/project/create",
                json={"name": "Character references"},
            ).json()["id"]
            seed_confirmed_segment(project_id)
            client.post("/world/create", json={"project_id": project_id})
            created = client.post(
                "/character/create",
                json={"project_id": project_id},
            )
            self.assertEqual(created.status_code, 200)
            self.assertTrue(created.json()["payload"]["negative_constraints"])

            mock_adapter = RecordingImageAdapter()
            original_image_adapter = main_module.character_image_adapter
            main_module.character_image_adapter = mock_adapter
            try:
                generated = client.post(
                    f"/projects/{project_id}/characters/references/generate",
                    json={"expected_version": created.json()["version"]},
                )
            finally:
                main_module.character_image_adapter = original_image_adapter
            self.assertEqual(generated.status_code, 200)
            generated_body = generated.json()
            references = generated_body["asset"]["payload"]["reference_images"]
            self.assertEqual(
                {item["framing"] for item in references},
                {"portrait", "half", "full"},
            )
            self.assertEqual(
                mock_adapter.calls,
                [
                    ("CHAR-001", "portrait"),
                    ("CHAR-001", "half"),
                    ("CHAR-001", "full"),
                ],
            )
            self.assertIsNotNone(generated_body["consistency_risk"])

            first = references[0]
            viewed = client.get(
                (
                    f"/projects/{project_id}/character-assets/"
                    f"{generated_body['asset']['id']}/references/{first['id']}"
                )
            )
            self.assertEqual(viewed.status_code, 200)
            self.assertEqual(viewed.headers["content-type"], "image/svg+xml")
            downloaded = client.get(
                (
                    f"/projects/{project_id}/character-assets/"
                    f"{generated_body['asset']['id']}/references/{first['id']}"
                    "?download=true"
                )
            )
            self.assertIn(
                "attachment",
                downloaded.headers["content-disposition"],
            )

            locked = client.patch(
                f"/projects/{project_id}/characters/references",
                json={
                    "expected_version": generated_body["asset"]["version"],
                    "selected_reference_ids": [item["id"] for item in references],
                    "locked": True,
                },
            )
            self.assertEqual(locked.status_code, 200)
            locked_body = locked.json()
            self.assertIsNone(locked_body["consistency_risk"])
            self.assertTrue(locked_body["asset"]["payload"]["locked"])

            blocked_regeneration = client.post(
                "/character/create",
                json={"project_id": project_id},
            )
            self.assertEqual(blocked_regeneration.status_code, 409)

            client.post("/story/create", json={"project_id": project_id})
            shots = client.post(
                "/shots/create",
                json={"project_id": project_id},
            )
            self.assertEqual(shots.status_code, 200)
            character_asset = locked_body["asset"]
            for shot in shots.json()["payload"]["shots"]:
                self.assertEqual(
                    shot["character_refs"],
                    [
                        {
                            "character_id": "CHAR-001",
                            "asset_id": character_asset["id"],
                            "version": character_asset["version"],
                        }
                    ],
                )

            unlocked = client.patch(
                f"/projects/{project_id}/characters/references",
                json={
                    "expected_version": character_asset["version"],
                    "selected_reference_ids": [item["id"] for item in references],
                    "locked": False,
                },
            )
            self.assertEqual(unlocked.status_code, 200)
            self.assertIsNotNone(unlocked.json()["consistency_risk"])
            self.assertTrue(
                any(
                    warning["kind"] == "shots"
                    and warning["upstream_kind"] == "character"
                    for warning in unlocked.json()["warnings"]
                )
            )

    def test_create_upload_and_refetch_project(self):
        with TestClient(app) as client:
            health = client.get("/health")
            self.assertEqual(health.status_code, 200)
            self.assertEqual(health.json()["storage"], "sqlite")

            cors = client.options(
                "/health",
                headers={
                    "Origin": "https://ai-emotion-director-web.vercel.app",
                    "Access-Control-Request-Method": "GET",
                },
            )
            self.assertEqual(cors.status_code, 200)
            self.assertEqual(
                cors.headers["access-control-allow-origin"],
                "https://ai-emotion-director-web.vercel.app",
            )

            created = client.post(
                "/project/create",
                json={"name": "T002 integration", "target_duration": 30},
            )
            self.assertEqual(created.status_code, 201)
            project_id = created.json()["id"]

            uploaded = client.post(
                "/audio/upload",
                data={"project_id": project_id},
                files={"audio": ("sample.wav", b"RIFF-demo-audio", "audio/wav")},
            )
            self.assertEqual(uploaded.status_code, 201)
            self.assertEqual(uploaded.json()["status"], "uploaded")

            fetched = client.get(f"/project/{project_id}")
            self.assertEqual(fetched.status_code, 200)
            snapshot = fetched.json()
            self.assertEqual(snapshot["name"], "T002 integration")
            self.assertEqual(snapshot["audio"]["filename"], "sample.wav")
            self.assertEqual(snapshot["audio"]["size_bytes"], len(b"RIFF-demo-audio"))

    def test_audio_analysis_is_real_versioned_and_cached(self):
        with TestClient(app) as client:
            created = client.post(
                "/project/create",
                json={"name": "Audio cache"},
            ).json()
            project_id = created["id"]
            audio_bytes = sine_wav_bytes()
            uploaded = client.post(
                "/audio/upload",
                data={"project_id": project_id},
                files={"audio": ("fixture.wav", audio_bytes, "audio/wav")},
            )
            self.assertEqual(uploaded.status_code, 201)

            first = client.post(
                "/audio/analyze",
                json={"project_id": project_id},
            )
            second = client.post(
                "/audio/analyze",
                json={"project_id": project_id},
            )
            self.assertEqual(first.status_code, 200)
            self.assertEqual(second.status_code, 200)
            self.assertFalse(first.json()["payload"]["degraded"])
            self.assertEqual(first.json()["asset_id"], second.json()["asset_id"])
            self.assertEqual(first.json()["version"], second.json()["version"])

    def test_project_crud_list_and_persistent_refetch(self):
        with TestClient(app) as client:
            first = client.post("/project/create", json={"name": "First project"}).json()
            second = client.post("/project/create", json={"name": "Second project"}).json()

            listed = client.get("/projects")
            self.assertEqual(listed.status_code, 200)
            listed_ids = {item["id"] for item in listed.json()["items"]}
            self.assertIn(first["id"], listed_ids)
            self.assertIn(second["id"], listed_ids)

            updated = client.patch(
                f"/projects/{first['id']}",
                json={"name": "First project renamed"},
            )
            self.assertEqual(updated.status_code, 200)
            self.assertEqual(updated.json()["name"], "First project renamed")

        with TestClient(app) as client:
            restored = client.get(f"/projects/{first['id']}")
            self.assertEqual(restored.status_code, 200)
            self.assertEqual(restored.json()["name"], "First project renamed")

    def test_delete_cascades_assets_jobs_and_media(self):
        with TestClient(app) as client:
            created = client.post("/project/create", json={"name": "Delete cascade"}).json()
            project_id = created["id"]
            uploaded = client.post(
                "/audio/upload",
                data={"project_id": project_id},
                files={"audio": ("delete.wav", b"RIFF-delete-me", "audio/wav")},
            )
            self.assertEqual(uploaded.status_code, 201)
            seed_confirmed_segment(project_id)
            self.assertEqual(client.post("/world/create", json={"project_id": project_id}).status_code, 200)
            character = client.post("/character/create", json={"project_id": project_id})
            self.assertEqual(character.status_code, 200)
            self.assertEqual(
                client.post(
                    f"/projects/{project_id}/characters/references/generate",
                    json={"expected_version": character.json()["version"]},
                ).status_code,
                200,
            )
            self.assertEqual(client.post("/story/create", json={"project_id": project_id}).status_code, 200)
            shots = client.post("/shots/create", json={"project_id": project_id})
            self.assertEqual(shots.status_code, 200)
            self.assertEqual(
                client.post(
                    f"/projects/{project_id}/keyframes/start",
                    json={"expected_shots_version": shots.json()["version"]},
                ).status_code,
                200,
            )
            self.assertEqual(client.post("/render/start", json={"project_id": project_id}).status_code, 202)

            before = count_project_dependents(project_id)
            self.assertGreater(before["audio_assets"], 0)
            self.assertGreater(before["generated_assets"], 0)
            self.assertGreater(before["render_jobs"], 0)

            deleted = client.delete(f"/projects/{project_id}")
            self.assertEqual(deleted.status_code, 204)
            self.assertEqual(
                count_project_dependents(project_id),
                {"audio_assets": 0, "generated_assets": 0, "render_jobs": 0},
            )
            self.assertEqual(client.get(f"/projects/{project_id}").status_code, 404)
            self.assertFalse((TEST_ROOT / "media" / "projects" / project_id).exists())

    def test_asset_versions_are_concurrent_safe_and_only_one_is_active(self):
        with TestClient(app) as client:
            project_id = UUID(
                client.post("/project/create", json={"name": "Concurrent versions"}).json()["id"]
            )

            def create_version(index: int):
                return insert_asset_version(
                    project_id,
                    "world",
                    {"marker": index},
                    activate=True,
                    provider="test",
                    model="concurrent",
                )

            with ThreadPoolExecutor(max_workers=6) as executor:
                list(executor.map(create_version, range(6)))

            versions = list_asset_versions(project_id, "world")
            self.assertEqual(sorted(asset["version"] for asset in versions), list(range(1, 7)))
            self.assertEqual(sum(asset["is_active"] for asset in versions), 1)
            self.assertEqual(
                client.get(f"/projects/{project_id}/assets").status_code,
                200,
            )

    def test_asset_rollback_warns_downstream_and_failed_version_stays_inactive(self):
        with TestClient(app) as client:
            project_id = client.post(
                "/project/create",
                json={"name": "Rollback dependencies"},
            ).json()["id"]
            seed_confirmed_segment(project_id)
            world_v1 = client.post("/world/create", json={"project_id": project_id}).json()
            world_v2 = client.post("/world/create", json={"project_id": project_id}).json()
            character = client.post(
                "/character/create",
                json={"project_id": project_id},
            )
            self.assertEqual(character.status_code, 200)

            failed = insert_asset_version(
                UUID(project_id),
                "world",
                {},
                activate=False,
                provider="test",
                model="broken",
                validation_errors=[{"message": "invalid payload"}],
            )
            self.assertEqual(failed["status"], "failed")
            active_before = next(
                asset
                for asset in list_asset_versions(UUID(project_id), "world")
                if asset["is_active"]
            )
            self.assertEqual(active_before["id"], world_v2["asset_id"])

            rollback = client.post(
                f"/projects/{project_id}/assets/world/activate",
                json={"version": world_v1["version"]},
            )
            self.assertEqual(rollback.status_code, 200)
            body = rollback.json()
            self.assertEqual(body["asset"]["id"], world_v1["asset_id"])
            self.assertTrue(
                any(
                    warning["kind"] == "character"
                    and warning["upstream_kind"] == "world"
                    for warning in body["warnings"]
                )
            )

            world_versions = list_asset_versions(UUID(project_id), "world")
            self.assertEqual(sum(asset["is_active"] for asset in world_versions), 1)
            self.assertFalse(next(asset for asset in world_versions if asset["id"] == failed["id"])["is_active"])
            context = load_project_context(UUID(project_id))
            self.assertEqual(
                context["asset_versions"]["world"]["asset_id"],
                world_v1["asset_id"],
            )

            failed_activation = client.post(
                f"/projects/{project_id}/assets/world/activate",
                json={"asset_id": failed["id"]},
            )
            self.assertEqual(failed_activation.status_code, 409)

    def test_invalid_generation_is_recorded_without_polluting_active_asset(self):
        with TestClient(app) as client:
            project_id = client.post(
                "/project/create",
                json={"name": "Schema failure isolation"},
            ).json()["id"]
            seed_confirmed_segment(project_id)
            active = client.post(
                "/world/create",
                json={"project_id": project_id},
            ).json()

            original_adapter = main_module.adapter
            main_module.adapter = AlwaysMalformedAdapter()
            try:
                failed_response = client.post(
                    "/world/create",
                    json={"project_id": project_id},
                )
            finally:
                main_module.adapter = original_adapter

            self.assertEqual(failed_response.status_code, 422)
            detail = failed_response.json()["detail"]
            self.assertTrue(detail["validation_errors"])

            versions = client.get(f"/projects/{project_id}/assets").json()["groups"]["world"]
            self.assertEqual(sum(asset["is_active"] for asset in versions), 1)
            self.assertEqual(
                next(asset for asset in versions if asset["is_active"])["id"],
                active["asset_id"],
            )
            failed = next(asset for asset in versions if asset["status"] == "failed")
            self.assertFalse(failed["is_active"])
            self.assertTrue(failed["validation_errors"])

    def test_provider_failure_is_visible_and_preserves_active_version(self):
        with TestClient(app) as client:
            project_id = client.post(
                "/project/create",
                json={"name": "Provider failure isolation"},
            ).json()["id"]
            seed_confirmed_segment(project_id)
            active = client.post(
                "/world/create",
                json={"project_id": project_id},
            ).json()

            original_adapter = main_module.adapter
            main_module.adapter = FailingProviderAdapter()
            try:
                response = client.post(
                    "/world/create",
                    json={"project_id": project_id},
                )
            finally:
                main_module.adapter = original_adapter

            self.assertEqual(response.status_code, 502)
            self.assertEqual(response.json()["detail"]["provider"], "mock-provider")
            versions = list_asset_versions(UUID(project_id), "world")
            self.assertEqual(
                next(asset for asset in versions if asset["is_active"])["id"],
                active["asset_id"],
            )
            failed = next(asset for asset in versions if asset["status"] == "failed")
            self.assertEqual(failed["provider"], "mock-provider")
            self.assertEqual(failed["model"], "mock-model")
            self.assertTrue(failed["prompt"])
            self.assertEqual(failed["validation_errors"][0]["status_code"], 429)

    def test_world_edit_lock_and_regenerate_preserve_locked_fields(self):
        with TestClient(app) as client:
            project_id = client.post(
                "/project/create",
                json={"name": "World Studio locks"},
            ).json()["id"]
            seed_confirmed_segment(project_id)
            first = client.post(
                "/world/create",
                json={"project_id": project_id},
            ).json()

            edited = client.patch(
                f"/projects/{project_id}/world",
                json={
                    "expected_version": first["version"],
                    "changes": {
                        "mutable_state": {"weather": "锁定的持续暴雨"},
                    },
                },
            )
            self.assertEqual(edited.status_code, 200)
            locked = client.patch(
                f"/projects/{project_id}/world",
                json={
                    "expected_version": edited.json()["asset"]["version"],
                    "changes": {},
                    "locked_fields": ["mutable_state.weather"],
                },
            )
            self.assertEqual(locked.status_code, 200)

            blocked_edit = client.patch(
                f"/projects/{project_id}/world",
                json={
                    "expected_version": locked.json()["asset"]["version"],
                    "changes": {
                        "mutable_state": {"weather": "不应被写入"},
                    },
                    "locked_fields": ["mutable_state.weather"],
                },
            )
            self.assertEqual(blocked_edit.status_code, 422)

            original_adapter = main_module.adapter
            main_module.adapter = ChangingWorldAdapter()
            try:
                regenerated = client.post(
                    "/world/create",
                    json={"project_id": project_id},
                )
            finally:
                main_module.adapter = original_adapter
            self.assertEqual(regenerated.status_code, 200)
            regenerated_payload = regenerated.json()["payload"]
            self.assertEqual(regenerated_payload["name"], "重新生成的世界")
            self.assertEqual(
                regenerated_payload["mutable_state"]["weather"],
                "锁定的持续暴雨",
            )
            self.assertEqual(
                regenerated_payload["locked_fields"],
                ["mutable_state.weather"],
            )

            conflict = client.patch(
                f"/projects/{project_id}/world",
                json={"expected_version": 1, "changes": {"name": "过期编辑"}},
            )
            self.assertEqual(conflict.status_code, 409)

            character = client.post(
                "/character/create",
                json={"project_id": project_id},
            )
            story = client.post(
                "/story/create",
                json={"project_id": project_id},
            )
            shots_response = client.post(
                "/shots/create",
                json={"project_id": project_id},
            )
            self.assertEqual(character.status_code, 200)
            self.assertEqual(story.status_code, 200)
            self.assertEqual(shots_response.status_code, 200)
            shots_asset = next(
                asset
                for asset in list_asset_versions(UUID(project_id), "shots")
                if asset["is_active"]
            )
            active_world = next(
                asset
                for asset in list_asset_versions(UUID(project_id), "world")
                if asset["is_active"]
            )
            self.assertEqual(
                shots_asset["input_snapshot"]["world"],
                {
                    "asset_id": active_world["id"],
                    "version": active_world["version"],
                },
            )

    def test_segment_recommend_confirm_bounds_and_dependency_invalidation(self):
        with TestClient(app) as client:
            project_id = client.post(
                "/project/create",
                json={"name": "Segment selection", "target_duration": 30},
            ).json()["id"]
            _, original_segment = seed_confirmed_segment(project_id, duration=90)

            recommendations = client.get(
                f"/projects/{project_id}/segments/recommendations"
            )
            self.assertEqual(recommendations.status_code, 200)
            self.assertEqual(
                {item["category"] for item in recommendations.json()["candidates"]},
                {"highlight", "turn", "stable"},
            )

            custom = client.post(
                f"/projects/{project_id}/segments/confirm",
                json={
                    "start": 10,
                    "end": 40,
                    "category": "custom",
                    "label": "10-40s",
                },
            )
            self.assertEqual(custom.status_code, 200)
            custom_segment = custom.json()["asset"]
            self.assertEqual(custom_segment["payload"]["start"], 10)
            self.assertNotEqual(custom_segment["id"], original_segment["id"])

            world = client.post(
                "/world/create",
                json={"project_id": project_id},
            )
            self.assertEqual(world.status_code, 200)
            world_asset = next(
                asset
                for asset in list_asset_versions(UUID(project_id), "world")
                if asset["is_active"]
            )
            self.assertEqual(
                world_asset["input_snapshot"]["segment"]["asset_id"],
                custom_segment["id"],
            )

            switched = client.post(
                f"/projects/{project_id}/segments/confirm",
                json={
                    "start": 20,
                    "end": 50,
                    "category": "custom",
                    "label": "20-50s",
                },
            )
            self.assertEqual(switched.status_code, 200)
            self.assertTrue(
                any(
                    warning["kind"] == "world"
                    and warning["upstream_kind"] == "segment"
                    for warning in switched.json()["warnings"]
                )
            )

            invalid_duration = client.post(
                f"/projects/{project_id}/segments/confirm",
                json={"start": 10, "end": 35},
            )
            self.assertEqual(invalid_duration.status_code, 422)
            outside_bounds = client.post(
                f"/projects/{project_id}/segments/confirm",
                json={"start": 70, "end": 100},
            )
            self.assertEqual(outside_bounds.status_code, 422)

            context = restrict_context_to_confirmed_segment(
                load_project_context(UUID(project_id))
            )
            self.assertEqual(context["assets"]["audio_analysis"]["duration"], 30)
            self.assertEqual(
                context["assets"]["audio_analysis"]["source_duration"],
                90,
            )
            self.assertLess(
                len(context["assets"]["audio_analysis"]["energy_curve"]),
                100,
            )

    def test_short_audio_cannot_produce_thirty_second_recommendations(self):
        with TestClient(app) as client:
            project_id = client.post(
                "/project/create",
                json={"name": "Short audio", "target_duration": 30},
            ).json()["id"]
            seed_confirmed_segment(project_id, duration=20)
            response = client.get(
                f"/projects/{project_id}/segments/recommendations"
            )
            self.assertEqual(response.status_code, 409)
            self.assertIn("shorter than target", response.json()["detail"])


if __name__ == "__main__":
    unittest.main()
