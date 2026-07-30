import unittest
from copy import deepcopy

from app.services.adapters import DemoDirectorAdapter
from app.services.shot_editor import (
    ShotEditError,
    canonicalize_shot_set,
    replace_single_shot,
)


class ShotEditorTest(unittest.TestCase):
    def setUp(self):
        self.payload = DemoDirectorAdapter().generate(
            "shots",
            {
                "asset_versions": {
                    "character": {"asset_id": 7, "version": 3},
                }
            },
        )

    def test_reorder_recomputes_start_and_start_ms(self):
        shots = self.payload["shots"]
        shots.insert(0, shots.pop(4))
        result = canonicalize_shot_set(self.payload, target_duration=30)
        self.assertEqual(result.shots[0].id, "S05")
        self.assertEqual(
            [shot.start_ms for shot in result.shots[:4]],
            [0, 3000, 6000, 9000],
        )

    def test_total_duration_mismatch_is_rejected(self):
        self.payload["shots"][0]["duration"] = 2
        with self.assertRaises(ShotEditError):
            canonicalize_shot_set(self.payload, target_duration=30)

    def test_single_regeneration_replaces_only_target(self):
        replacement = deepcopy(self.payload["shots"][3])
        replacement["action"] = "仅此镜头改变"
        result = replace_single_shot(
            self.payload,
            "S04",
            replacement,
            target_duration=30,
        )
        changed = [
            after.id
            for before, after in zip(self.payload["shots"], result.shots)
            if before != after.model_dump(mode="json")
        ]
        self.assertEqual(changed, ["S04"])


if __name__ == "__main__":
    unittest.main()
