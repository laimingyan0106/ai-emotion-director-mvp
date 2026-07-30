import os
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from uuid import UUID

from fastapi.testclient import TestClient


TEST_ROOT = Path(tempfile.mkdtemp(prefix="emotion-director-api-"))
os.environ["STORAGE_MODE"] = "sqlite"
os.environ["SQLITE_PATH"] = str(TEST_ROOT / "test.db")
os.environ["MEDIA_ROOT"] = str(TEST_ROOT / "media")

from app.main import app  # noqa: E402
from app.database import (  # noqa: E402
    count_project_dependents,
    insert_asset_version,
    list_asset_versions,
    load_project_context,
)


class ApiIntegrationTest(unittest.TestCase):
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
            self.assertEqual(client.post("/world/create", json={"project_id": project_id}).status_code, 200)
            self.assertEqual(client.post("/shots/create", json={"project_id": project_id}).status_code, 200)
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


if __name__ == "__main__":
    unittest.main()
