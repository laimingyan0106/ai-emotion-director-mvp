import base64
import json
import unittest

import httpx

from app.config import Settings
from app.services.keyframes import (
    DemoKeyframeImageAdapter,
    OpenAIKeyframeImageAdapter,
    get_keyframe_image_adapter,
    sanitize_provider_error,
    _validated_remote_image_url,
)


class KeyframeProviderTest(unittest.IsolatedAsyncioTestCase):
    async def test_openai_provider_decodes_image_and_tracks_request_id(self):
        image = b"\x89PNG\r\n\x1a\nprovider-test"

        async def handler(request: httpx.Request) -> httpx.Response:
            self.assertEqual(request.url.path, "/v1/images/generations")
            self.assertEqual(request.headers["authorization"], "Bearer test-secret")
            body = json.loads(request.content)
            self.assertEqual(body["model"], "gpt-image-2")
            self.assertEqual(body["size"], "1280x720")
            self.assertNotIn("quality", body)
            self.assertNotIn("output_format", body)
            return httpx.Response(
                200,
                headers={"x-request-id": "req_provider_acceptance"},
                json={"data": [{"b64_json": base64.b64encode(image).decode()}]},
            )

        settings = Settings(
            _env_file=None,
            adapter_mode="provider",
            image_api_key="test-secret",
        )
        adapter = OpenAIKeyframeImageAdapter(
            settings,
            transport=httpx.MockTransport(handler),
        )
        result = await adapter.generate(shot_id="S01", prompt="cinematic frame")
        self.assertEqual(result.content, image)
        self.assertEqual(result.content_type, "image/png")
        self.assertEqual((result.width, result.height), (1280, 720))
        self.assertEqual(result.provider_task_id, "req_provider_acceptance")

    async def test_provider_error_does_not_echo_response_or_key(self):
        async def handler(_: httpx.Request) -> httpx.Response:
            return httpx.Response(
                401,
                headers={"x-request-id": "req_denied"},
                json={"error": {"message": "secret sk-testing-only-should-not-leak"}},
            )

        settings = Settings(
            _env_file=None,
            adapter_mode="provider",
            image_api_key="sk-live-testing-only",
        )
        adapter = OpenAIKeyframeImageAdapter(
            settings,
            transport=httpx.MockTransport(handler),
        )
        with self.assertRaisesRegex(RuntimeError, "HTTP 401.*req_denied") as raised:
            await adapter.generate(shot_id="S01", prompt="frame")
        message = str(raised.exception)
        self.assertNotIn("sk-testing-only", message)
        self.assertNotIn("should-not-leak", message)
        self.assertIn("detail=", message)

    async def test_openai_provider_downloads_url_response(self):
        image = b"\x89PNG\r\n\x1a\nrelay-url-test"

        async def handler(request: httpx.Request) -> httpx.Response:
            if request.method == "POST":
                return httpx.Response(
                    200,
                    json={"data": [{"url": "https://cdn.relay.test/frame.png"}]},
                )
            self.assertEqual(str(request.url), "https://cdn.relay.test/frame.png")
            return httpx.Response(200, content=image)

        settings = Settings(
            _env_file=None,
            adapter_mode="provider",
            image_api_key="test-secret",
        )
        adapter = OpenAIKeyframeImageAdapter(
            settings,
            transport=httpx.MockTransport(handler),
        )
        result = await adapter.generate(shot_id="S01", prompt="frame")
        self.assertEqual(result.content, image)

    async def test_relay_can_use_raw_authorization_header(self):
        async def handler(request: httpx.Request) -> httpx.Response:
            self.assertEqual(request.headers["authorization"], "test-secret")
            return httpx.Response(
                200,
                json={"data": [{"b64_json": base64.b64encode(b"png").decode()}]},
            )

        settings = Settings(
            _env_file=None,
            image_api_key="test-secret",
            image_auth_style="raw",
        )
        adapter = OpenAIKeyframeImageAdapter(
            settings,
            transport=httpx.MockTransport(handler),
        )
        await adapter.generate(shot_id="S01", prompt="frame")

    def test_provider_mode_without_key_falls_back_explicitly(self):
        settings = Settings(
            _env_file=None,
            adapter_mode="provider",
            image_api_key=None,
            llm_api_key=None,
        )
        adapter = get_keyframe_image_adapter(settings)
        self.assertIsInstance(adapter, DemoKeyframeImageAdapter)
        self.assertIn("missing", adapter.fallback_reason)

    def test_image_provider_can_run_with_demo_director(self):
        settings = Settings(
            _env_file=None,
            adapter_mode="demo",
            image_adapter_mode="provider",
            image_api_key="test-secret",
        )
        adapter = get_keyframe_image_adapter(settings)
        self.assertIsInstance(adapter, OpenAIKeyframeImageAdapter)

    def test_sanitizer_redacts_credentials(self):
        message = sanitize_provider_error(
            RuntimeError("Authorization: Bearer sk-secret-123456789 api_key=topsecret")
        )
        self.assertNotIn("sk-secret", message)
        self.assertNotIn("topsecret", message)

    def test_sanitizer_keeps_exception_type_for_empty_timeout_message(self):
        self.assertEqual(sanitize_provider_error(httpx.ReadTimeout("")), "ReadTimeout")

    def test_image_url_rejects_private_network_targets(self):
        with self.assertRaises(ValueError):
            _validated_remote_image_url("http://127.0.0.1/frame.png")
        with self.assertRaises(ValueError):
            _validated_remote_image_url("https://169.254.169.254/latest/meta-data")
