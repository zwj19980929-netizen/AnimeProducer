"""
DeepSeek LLM 客户端
使用 OpenAI 兼容接口
"""
import json
import logging
from typing import Optional
import requests

from pydantic import BaseModel
from config import settings
from integrations.base_client import BaseLLMClient, QuotaExceededError, AuthenticationError

logger = logging.getLogger(__name__)


class DeepSeekClient(BaseLLMClient):
    """DeepSeek LLM 客户端"""
    
    provider_name: str = "deepseek"
    
    def __init__(self):
        self.api_key = settings.DEEPSEEK_API_KEY
        self.model = settings.DEEPSEEK_MODEL
        self.endpoint = settings.DEEPSEEK_ENDPOINT
        
        if not self.api_key:
            logger.warning("DEEPSEEK_API_KEY 未配置")
    
    def generate_structured_output(
        self,
        prompt: str,
        pydantic_model,
        temperature: float = 0.2
    ):
        """使用 DeepSeek 生成结构化输出"""
        if not self.api_key:
            raise AuthenticationError("DEEPSEEK_API_KEY 未配置")
        
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        # 构建 JSON schema 指令
        schema = pydantic_model.model_json_schema()
        format_instruction = f"请严格按照以下 JSON 格式返回结果，不要添加任何额外文字:\n{json.dumps(schema, ensure_ascii=False, indent=2)}"
        
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": "你是一个专业的 AI 助手。请只返回符合要求的 JSON，不要包含任何其他内容。"},
                {"role": "user", "content": f"{format_instruction}\n\n{prompt}"}
            ],
            "temperature": temperature,
            "response_format": {"type": "json_object"}
        }
        
        try:
            response = requests.post(
                f"{self.endpoint}/chat/completions",
                headers=headers,
                json=payload,
                timeout=120
            )
            
            if response.status_code == 429:
                raise QuotaExceededError("DeepSeek API 限流")
            if response.status_code in (401, 403):
                raise AuthenticationError("DeepSeek 认证失败")
            
            response.raise_for_status()
            result = response.json()
            
            content = result["choices"][0]["message"]["content"]
            
            # 清理可能的 markdown 代码块
            if content.startswith("```"):
                content = content.split("```")[1]
                if content.startswith("json"):
                    content = content[4:]
            content = content.strip()
            
            # 解析 JSON 并验证
            data = json.loads(content)
            return pydantic_model.model_validate(data)
            
        except json.JSONDecodeError as e:
            logger.error(f"DeepSeek 返回的 JSON 解析失败: {e}")
            return None
        except requests.exceptions.RequestException as e:
            logger.error(f"DeepSeek API 请求失败: {e}")
            return None
    
    def health_check(self) -> bool:
        return bool(self.api_key)


deepseek_client = DeepSeekClient()
