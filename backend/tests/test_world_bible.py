import unittest

from app.services.adapters import DemoDirectorAdapter
from app.services.prompts import prompt_context_for_task
from app.services.world import preserve_locked_world_fields


class WorldBibleTest(unittest.TestCase):
    def test_world_schema_is_structured_not_prose(self):
        world = DemoDirectorAdapter().generate("world", {})
        self.assertIn("immutable_rules", world)
        self.assertIn("mutable_state", world)
        self.assertIn("visual_exclusions", world["immutable_rules"])
        self.assertIn("cinematography", world["immutable_rules"])
        self.assertIsInstance(world["immutable_rules"]["architecture"], list)

    def test_locked_field_is_preserved_after_regeneration(self):
        current = DemoDirectorAdapter().generate("world", {})
        current["mutable_state"]["weather"] = "永续暴雨"
        current["locked_fields"] = ["mutable_state.weather"]
        generated = DemoDirectorAdapter().generate("world", {})
        generated["name"] = "新世界名"
        generated["mutable_state"]["weather"] = "晴朗"
        preserved = preserve_locked_world_fields(current, generated)
        self.assertEqual(preserved.name, "新世界名")
        self.assertEqual(preserved.mutable_state.weather, "永续暴雨")

    def test_shot_prompt_context_contains_only_visual_world_fields(self):
        world = DemoDirectorAdapter().generate("world", {})
        context = {
            "project": {"target_duration": 30},
            "assets": {"world": world, "segment": {"start": 0, "end": 30}},
        }
        prompt_context = prompt_context_for_task("shots", context)
        shot_world = prompt_context["assets"]["world"]
        self.assertIn("cinematography", shot_world)
        self.assertIn("visual_exclusions", shot_world)
        self.assertNotIn("culture", shot_world)
        self.assertNotIn("emotion_theme", shot_world)
        self.assertNotIn("public_mood", shot_world)


if __name__ == "__main__":
    unittest.main()
