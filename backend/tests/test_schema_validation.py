import unittest
from copy import deepcopy
from typing import Any

from pydantic import ValidationError

from app.domain import validate_domain_asset
from app.services.adapters import DemoDirectorAdapter, DirectorAdapter
from app.services.generation import AssetGenerationError, generate_validated_asset


class SequencedAdapter(DirectorAdapter):
    def __init__(self, outputs: list[Any]) -> None:
        self.outputs = iter(outputs)
        self.repair_calls = 0

    def generate(self, task: str, context: dict[str, Any]) -> Any:
        return next(self.outputs)

    def repair(
        self,
        task: str,
        invalid_output: Any,
        validation_errors: list[dict[str, Any]],
        context: dict[str, Any],
    ) -> Any:
        self.repair_calls += 1
        return next(self.outputs)


class SchemaValidationTest(unittest.TestCase):
    def setUp(self):
        self.context = {
            "project": {"target_duration": 30},
            "assets": {"character": DemoDirectorAdapter().generate("character", {})},
        }

    def test_malformed_json_is_repaired_once(self):
        valid_world = DemoDirectorAdapter().generate("world", {})
        adapter = SequencedAdapter(["{not-json", valid_world])
        result = generate_validated_asset(
            adapter,
            "world",
            self.context,
            retry_attempts=1,
        )
        self.assertEqual(result.model.name, valid_world["name"])
        self.assertEqual(adapter.repair_calls, 1)
        self.assertTrue(result.validation_errors)
        self.assertEqual(result.validation_errors[0]["attempt"], 1)

    def test_retry_budget_is_configurable_and_errors_are_not_swallowed(self):
        adapter = SequencedAdapter(["[]"])
        with self.assertRaises(AssetGenerationError) as raised:
            generate_validated_asset(
                adapter,
                "world",
                self.context,
                retry_attempts=0,
            )
        self.assertEqual(len(raised.exception.validation_errors), 1)
        self.assertEqual(raised.exception.validation_errors[0]["type"], "TypeError")

    def test_shot_total_must_match_project_target(self):
        payload = deepcopy(DemoDirectorAdapter().generate("shots", {}))
        payload["shots"][-1]["duration"] = 2
        payload["duration"] = 29
        with self.assertRaises(ValueError) as raised:
            validate_domain_asset("shots", payload, self.context)
        self.assertIn("project target", str(raised.exception))

    def test_unknown_character_reference_is_rejected(self):
        payload = deepcopy(DemoDirectorAdapter().generate("shots", {}))
        payload["shots"][0]["character_ids"] = ["CHAR-999"]
        payload["shots"][0]["character_refs"][0]["character_id"] = "CHAR-999"
        with self.assertRaises(ValueError) as raised:
            validate_domain_asset("shots", payload, self.context)
        self.assertIn("unknown characters", str(raised.exception))

    def test_extra_fields_are_rejected(self):
        payload = DemoDirectorAdapter().generate("world", {})
        payload["unexpected"] = True
        with self.assertRaises(ValidationError):
            validate_domain_asset("world", payload, self.context)


if __name__ == "__main__":
    unittest.main()
