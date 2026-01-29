"""
豆包 (字节跳动) LLM 客户端
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


class DoubaoClient(BaseLLMClient):
    """豆包 LLM 客户端 (火山方舟)"""
    
    provider_name: str = "doubao"
    
    def __init__(self):
        self.api_key = settings.DOUBAO_API_KEY
        self.model = settings.DOUBAO_MODEL
        self.endpoint = settings.DOUBAO_ENDPOINT
        
        if not self.api_key:
            logger.warning("DOUBAO_API_KEY 未配置")
    
    def generate_structured_output(
        self,
        prompt: str,
        pydantic_model,
        temperature: float = 0.2
    ):
        """使用豆包生成结构化输出"""
        if not self.api_key:
            raise AuthenticationError("DOUBAO_API_KEY 未配置")
        
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        # 构建 JSON schema 指令
        schema = pydantic_model.model_json_schema()
        format_instruction = f"请严格按照以下 JSON 格式返回结果:\n{json.dumps(schema, ensure_ascii=False, indent=2)}"
        
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": "你是一个专业的 AI 助手，请严格按照要求的 JSON 格式输出。"},
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
                raise QuotaExceededError("豆包 API 限流")
            if response.status_code in (401, 403):
                raise AuthenticationError("豆包认证失败")
            
            response.raise_for_status()
            result = response.json()
            
            content = result["choices"][0]["message"]["content"]
            
            # 解析 JSON 并验证
            data = json.loads(content)
            return pydantic_model.model_validate(data)
            
        except json.JSONDecodeError as e:
            logger.error(f"豆包返回的 JSON 解析失败: {e}")
            return None
        except requests.exceptions.RequestException as e:
            logger.error(f"豆包 API 请求失败: {e}")
            return None
    
    def health_check(self) -> bool:
        return bool(self.api_key)


doubao_client = DoubaoClient()
