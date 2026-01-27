import unittest
from unittest.mock import MagicMock, patch
from core.script_parser import ScriptParser, Storyboard
from core.models import Shot

class TestScriptParser(unittest.TestCase):

    @patch('core.script_parser.llm_client')
    def test_parse_novel_to_storyboard(self, mock_llm_client):
        # Setup mock return value
        mock_shots = [
            Shot(
                shot_id=1,
                duration=3.0,
                scene_description="Hero walks in",
                visual_prompt="A hero walking in a dark alley",
                camera_movement="pan_right",
                characters_in_shot=["Hero"],
                dialogue="I am here.",
                action_type="walking"
            )
        ]
        mock_storyboard = Storyboard(shots=mock_shots)
        mock_llm_client.generate_structured_output.return_value = mock_storyboard

        parser = ScriptParser()
        result = parser.parse_novel_to_storyboard("Hero walks in and says I am here.")

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].scene_description, "Hero walks in")
        self.assertEqual(result[0].duration, 3.0)
        self.assertIsInstance(result[0], Shot)

if __name__ == '__main__':
    unittest.main()
