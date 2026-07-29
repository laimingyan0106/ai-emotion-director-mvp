import unittest

from app.services.adapters import DemoDirectorAdapter
from app.services.audio import demo_analysis


class DirectorPipelineTest(unittest.TestCase):
    def test_demo_analysis_has_30_second_directing_signals(self):
        result = demo_analysis()
        self.assertEqual(result["duration"], 30.0)
        self.assertEqual(len(result["emotion_curve"]), 20)
        self.assertEqual(result["peaks"][1]["time"], 17)

    def test_director_pipeline_creates_complete_plan(self):
        adapter = DemoDirectorAdapter()
        context = {"audio_analysis": demo_analysis()}
        world = adapter.generate("world", context)
        character = adapter.generate("character", {**context, "world": world})
        story = adapter.generate("story", {**context, "world": world, "character": character})
        result = adapter.generate("shots", {**context, "world": world, "character": character, "story": story})

        self.assertEqual(world["name"], "潮汐之上的城")
        self.assertEqual(character["id"], "CHAR-001")
        self.assertEqual(len(story["acts"]), 3)
        self.assertEqual(result["duration"], 30)
        self.assertEqual(len(result["shots"]), 10)
        self.assertEqual(sum(shot["duration"] for shot in result["shots"]), 30)
        self.assertTrue(all(shot["prompt"] for shot in result["shots"]))


if __name__ == "__main__":
    unittest.main()
