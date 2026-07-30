import json
import unittest
from unittest.mock import patch

import httpx

from app.config import Settings
from app.services.adapters import (
    DemoDirectorAdapter,
    ProviderDirectorAdapter,
    get_director_adapter,
)
from app.services.generation import generate_validated_asset
from app.services.providers import OpenAIResponsesClient


def world_payload():
    return DemoDirectorAdapter().generate("world", {})


class ProviderAdapterTest(unittest.TestCase):
    def test_missing_key_falls_back_to_complete_demo(self):
        with patch.dict("os.environ", {}, clear=True):
            adapter = get_director_adapter(
                Settings(
                    adapter_mode="provider",
                    llm_api_key=None,
                    _env_file=None,
                )
            )
        self.assertIsInstance(adapter, DemoDirectorAdapter)
        self.assertEqual(adapter.fallback_reason, "missing_llm_api_key")
        self.assertEqual(adapter.generate("world", {})["name"], world_payload()["name"])

    def test_mock_responses_provider_returns_schema_valid_asset(self):
        captured = {}

        def handler(request: httpx.Request):
            captured["authorization"] = request.headers["authorization"]
            captured["body"] = json.loads(request.content)
            return httpx.Response(
                200,
                json={
                    "output": [
                        {
                            "type": "message",
                            "content": [
                                {
                                    "type": "output_text",
                                    "text": json.dumps(world_payload(), ensure_ascii=False),
                                }
                            ],
                        }
                    ]
                },
            )

        client = OpenAIResponsesClient(
            api_key="test-secret-never-log",
            base_url="https://api.openai.test/v1",
            timeout_seconds=10,
            http_retries=0,
            transport=httpx.MockTransport(handler),
        )
        adapter = ProviderDirectorAdapter(client=client, model="gpt-test")
        context = {
            "project": {"target_duration": 30},
            "assets": {
                "segment": {"start": 0, "end": 30, "confirmed": True},
                "audio_analysis": {"duration": 30, "energy_curve": [0.1, 0.8]},
            },
        }
        result = generate_validated_asset(
            adapter,
            "world",
            context,
            retry_attempts=0,
        )
        self.assertEqual(result.model.name, world_payload()["name"])
        self.assertEqual(captured["body"]["model"], "gpt-test")
        self.assertEqual(
            captured["body"]["text"]["format"]["type"],
            "json_schema",
        )
        self.assertTrue(captured["body"]["text"]["format"]["strict"])
        self.assertNotIn("test-secret-never-log", json.dumps(captured["body"]))
        self.assertEqual(captured["authorization"], "Bearer test-secret-never-log")

    def test_rate_limit_is_retried_with_bounded_policy(self):
        calls = []
        sleeps = []

        def handler(request: httpx.Request):
            calls.append(request)
            if len(calls) == 1:
                return httpx.Response(429, headers={"retry-after": "0"})
            return httpx.Response(
                200,
                json={"output_text": json.dumps(world_payload(), ensure_ascii=False)},
            )

        client = OpenAIResponsesClient(
            api_key="test-key",
            base_url="https://api.openai.test/v1",
            timeout_seconds=10,
            http_retries=1,
            transport=httpx.MockTransport(handler),
            sleeper=sleeps.append,
        )
        result = client.create_structured(
            model="gpt-test",
            instructions="test",
            prompt="test",
            schema_name="world",
            schema={},
        )
        self.assertEqual(result["name"], world_payload()["name"])
        self.assertEqual(len(calls), 2)
        self.assertEqual(sleeps, [0.0])

    def test_chat_completions_style_returns_schema_valid_asset(self):
        captured = {}

        def handler(request: httpx.Request):
            captured["path"] = request.url.path
            captured["body"] = json.loads(request.content)
            return httpx.Response(
                200,
                json={
                    "choices": [
                        {
                            "message": {
                                "content": json.dumps(
                                    world_payload(),
                                    ensure_ascii=False,
                                )
                            }
                        }
                    ]
                },
            )

        client = OpenAIResponsesClient(
            api_key="test-secret-never-log",
            base_url="https://relay.test/v1",
            timeout_seconds=10,
            http_retries=0,
            api_style="chat_completions",
            transport=httpx.MockTransport(handler),
        )
        result = client.create_structured(
            model="gpt-test",
            instructions="director",
            prompt="world",
            schema_name="world",
            schema={},
        )
        self.assertEqual(result["name"], world_payload()["name"])
        self.assertEqual(captured["path"], "/v1/chat/completions")
        self.assertEqual(captured["body"]["messages"][0]["role"], "system")
        self.assertEqual(
            captured["body"]["response_format"]["type"],
            "json_schema",
        )


if __name__ == "__main__":
    unittest.main()
