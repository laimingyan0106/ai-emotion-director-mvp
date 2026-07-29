import os
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient


TEST_ROOT = Path(tempfile.mkdtemp(prefix="emotion-director-api-"))
os.environ["STORAGE_MODE"] = "sqlite"
os.environ["SQLITE_PATH"] = str(TEST_ROOT / "test.db")
os.environ["MEDIA_ROOT"] = str(TEST_ROOT / "media")

from app.main import app  # noqa: E402


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


if __name__ == "__main__":
    unittest.main()
