"""
AI 影评人模块测试

测试 VideoCritic 的评分功能和响应解析。
"""

import json
import unittest
from unittest.mock import MagicMock, patch, PropertyMock

from core.critic import VideoCritic, VideoReview, get_video_critic


class TestVideoReview(unittest.TestCase):
    """测试 VideoReview 数据类"""

    def test_video_review_creation(self):
        """测试创建 VideoReview 对象"""
        review = VideoReview(
            score=8,
            has_glitches=False,
            feedback="Good quality",
            details={"anatomy": 9, "temporal_consistency": 8},
        )

        self.assertEqual(review.score, 8)
        self.assertFalse(review.has_glitches)
        self.assertEqual(review.feedback, "Good quality")
        self.assertEqual(review.details["anatomy"], 9)

    def test_video_review_defaults(self):
        """测试 VideoReview 默认值"""
        review = VideoReview(score=5, has_glitches=True, feedback="")

        self.assertEqual(review.details, {})
        self.assertEqual(review.raw_response, "")


class TestVideoCritic(unittest.TestCase):
    """测试 VideoCritic 类"""

    @patch('core.critic.settings')
    def test_parse_valid_response(self, mock_settings):
        """测试解析有效的 JSON 响应"""
        mock_settings.GOOGLE_API_KEY = "test_key"
        mock_settings.VLM_BACKEND = "gemini"

        with patch.object(VideoCritic, '_init_client'):
            critic = VideoCritic()

        response_text = json.dumps({
            "score": 9,
            "has_glitches": False,
            "feedback": "Excellent quality",
            "details": {
                "anatomy": 10,
                "temporal_consistency": 9,
                "prompt_match": 8,
                "animation_quality": 9
            }
        })

        review = critic._parse_response(response_text)

        self.assertEqual(review.score, 9)
        self.assertFalse(review.has_glitches)
        self.assertEqual(review.feedback, "Excellent quality")
        self.assertEqual(review.details["anatomy"], 10)

    @patch('core.critic.settings')
    def test_parse_markdown_wrapped_response(self, mock_settings):
        """测试解析带 markdown 代码块的响应"""
        mock_settings.GOOGLE_API_KEY = "test_key"
        mock_settings.VLM_BACKEND = "gemini"

        with patch.object(VideoCritic, '_init_client'):
            critic = VideoCritic()

        response_text = """```json
{
    "score": 7,
    "has_glitches": true,
    "feedback": "Minor flickering detected"
}
```"""

        review = critic._parse_response(response_text)

        self.assertEqual(review.score, 7)
        self.assertTrue(review.has_glitches)
        self.assertEqual(review.feedback, "Minor flickering detected")

    @patch('core.critic.settings')
    def test_parse_invalid_response(self, mock_settings):
        """测试解析无效响应时的降级处理"""
        mock_settings.GOOGLE_API_KEY = "test_key"
        mock_settings.VLM_BACKEND = "gemini"

        with patch.object(VideoCritic, '_init_client'):
            critic = VideoCritic()

        response_text = "This is not valid JSON"

        review = critic._parse_response(response_text)

        # 应该返回保守的默认值
        self.assertEqual(review.score, 5)
        self.assertTrue(review.has_glitches)
        self.assertIn("Unable to parse", review.feedback)

    @patch('core.critic.settings')
    def test_is_acceptable(self, mock_settings):
        """测试质量判断逻辑"""
        mock_settings.GOOGLE_API_KEY = "test_key"
        mock_settings.VLM_BACKEND = "gemini"
        mock_settings.CRITIC_MIN_SCORE = 8  # 添加配置值

        with patch.object(VideoCritic, '_init_client'):
            critic = VideoCritic(pass_score=8)

        # 分数达标
        review_pass = VideoReview(score=8, has_glitches=False, feedback="")
        self.assertTrue(critic.is_acceptable(review_pass))

        # 分数超标
        review_excellent = VideoReview(score=10, has_glitches=False, feedback="")
        self.assertTrue(critic.is_acceptable(review_excellent))

        # 分数不达标
        review_fail = VideoReview(score=7, has_glitches=True, feedback="Issues found")
        self.assertFalse(critic.is_acceptable(review_fail))

    @patch('core.critic.settings')
    def test_build_eval_prompt(self, mock_settings):
        """测试评估提示词构建"""
        mock_settings.GOOGLE_API_KEY = "test_key"
        mock_settings.VLM_BACKEND = "gemini"

        with patch.object(VideoCritic, '_init_client'):
            critic = VideoCritic()

        prompt = critic._build_eval_prompt(
            original_prompt="A hero standing in the rain",
            characters=["Hero", "Villain"]
        )

        self.assertIn("A hero standing in the rain", prompt)
        self.assertIn("Hero, Villain", prompt)
        self.assertIn("evaluate this video", prompt.lower())

    @patch('core.critic.settings')
    def test_build_eval_prompt_no_characters(self, mock_settings):
        """测试无角色时的提示词构建"""
        mock_settings.GOOGLE_API_KEY = "test_key"
        mock_settings.VLM_BACKEND = "gemini"

        with patch.object(VideoCritic, '_init_client'):
            critic = VideoCritic()

        prompt = critic._build_eval_prompt(
            original_prompt="A beautiful sunset",
            characters=None
        )

        self.assertIn("A beautiful sunset", prompt)
        self.assertNotIn("Characters in scene", prompt)


class TestGetVideoCritic(unittest.TestCase):
    """测试单例获取函数"""

    @patch('core.critic.settings')
    @patch('core.critic.video_critic', None)
    def test_get_video_critic_singleton(self, mock_settings):
        """测试单例模式"""
        mock_settings.GOOGLE_API_KEY = "test_key"
        mock_settings.VLM_BACKEND = "gemini"
        mock_settings.CRITIC_PROVIDER = "gemini"
        mock_settings.CRITIC_MODEL = "gemini-1.5-pro"

        with patch.object(VideoCritic, '_init_client'):
            critic1 = get_video_critic()
            critic2 = get_video_critic()

            # 应该返回同一个实例
            self.assertIs(critic1, critic2)


if __name__ == '__main__':
    unittest.main()
