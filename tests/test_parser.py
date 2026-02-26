import unittest
from unittest.mock import patch
from core.script_parser import ScriptParser, Storyboard, ShotDraft

class TestScriptParser(unittest.TestCase):

    @patch('integrations.llm_client.llm_client')
    def test_parse_novel_to_storyboard(self, mock_llm_client):
        # Setup mock return value
        mock_shots = [
            ShotDraft(
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
        self.assertIsInstance(result[0], ShotDraft)

if __name__ == '__main__':
    unittest.main()
