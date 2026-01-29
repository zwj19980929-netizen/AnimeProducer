"""
Provider Factory - 多厂商模型网关
支持 Google、Replicate、火山引擎、阿里万相、豆包、DeepSeek 等
"""
import logging
from typing import List, Optional, Dict, Any

from config import settings
from integrations.base_client import (
    BaseImageClient, 
    BaseVideoClient, 
    BaseLLMClient,
    QuotaExceededError,
    AuthenticationError
)

logger = logging.getLogger(__name__)


class ProviderFactory:
    """多厂商模型网关工厂"""
    
    # 缓存已创建的客户端实例
    _image_clients: Dict[str, BaseImageClient] = {}
    _video_clients: Dict[str, BaseVideoClient] = {}
    _llm_clients: Dict[str, BaseLLMClient] = {}
    
    # ========== Image Clients ==========
    
    @classmethod
    def get_image_client(cls, provider: Optional[str] = None) -> BaseImageClient:
        """
        获取图像生成客户端
        
        Args:
            provider: google, replicate, aliyun
        """
        provider = provider or settings.IMAGE_PROVIDER
        
        if provider not in cls._image_clients:
            cls._image_clients[provider] = cls._create_image_client(provider)
        
        return cls._image_clients[provider]
    
    @classmethod
    def _create_image_client(cls, provider: str) -> BaseImageClient:
        """创建图像客户端实例"""
        if provider == "google":
            from integrations.gen_client import gen_client
            return gen_client
        elif provider == "aliyun":
            from integrations.aliyun_client import aliyun_image_client
            return aliyun_image_client
        elif provider == "replicate":
            raise NotImplementedError("Replicate 图像客户端待实现")
        else:
            raise ValueError(f"未知的图像 Provider: {provider}")
    
    @classmethod
    def get_backup_image_providers(cls) -> List[str]:
        """获取备用图像 Provider 列表"""
        backup_str = settings.BACKUP_IMAGE_PROVIDERS
        return [p.strip() for p in backup_str.split(",") if p.strip()]
    
    # ========== Video Clients ==========
    
    @classmethod
    def get_video_client(cls, provider: Optional[str] = None) -> BaseVideoClient:
        """
        获取视频生成客户端
        
        Args:
            provider: google, replicate, volcengine, aliyun
        """
        provider = provider or settings.VIDEO_PROVIDER
        
        if provider not in cls._video_clients:
            cls._video_clients[provider] = cls._create_video_client(provider)
        
        return cls._video_clients[provider]
    
    @classmethod
    def _create_video_client(cls, provider: str) -> BaseVideoClient:
        """创建视频客户端实例"""
        if provider in ("google", "google_veo"):
            from integrations.video_client import video_client
            return video_client
        elif provider == "replicate":
            from integrations.replicate_client import replicate_video_client
            return replicate_video_client
        elif provider == "volcengine":
            from integrations.volcengine_client import volcengine_video_client
            return volcengine_video_client
        elif provider == "aliyun":
            from integrations.aliyun_client import aliyun_video_client
            return aliyun_video_client
        else:
            raise ValueError(f"未知的视频 Provider: {provider}")
    
    @classmethod
    def get_backup_video_providers(cls) -> List[str]:
        """获取备用视频 Provider 列表"""
        backup_str = settings.BACKUP_VIDEO_PROVIDERS
        return [p.strip() for p in backup_str.split(",") if p.strip()]
    
    # ========== LLM Clients ==========
    
    @classmethod
    def get_llm_client(cls, provider: Optional[str] = None) -> BaseLLMClient:
        """
        获取 LLM 客户端
        
        Args:
            provider: google, openai, doubao, deepseek
        """
        provider = provider or settings.LLM_PROVIDER
        
        if provider not in cls._llm_clients:
            cls._llm_clients[provider] = cls._create_llm_client(provider)
        
        return cls._llm_clients[provider]
    
    @classmethod
    def _create_llm_client(cls, provider: str) -> BaseLLMClient:
        """创建 LLM 客户端实例"""
        if provider == "google":
            from integrations.llm_client import llm_client
            # 包装现有客户端以符合接口
            return cls._wrap_legacy_llm_client(llm_client, "google")
        elif provider == "doubao":
            from integrations.doubao_client import doubao_client
            return doubao_client
        elif provider == "deepseek":
            from integrations.deepseek_client import deepseek_client
            return deepseek_client
        elif provider == "openai":
            raise NotImplementedError("OpenAI LLM 客户端待实现")
        else:
            raise ValueError(f"未知的 LLM Provider: {provider}")
    
    @classmethod
    def _wrap_legacy_llm_client(cls, client, provider_name: str):
        """包装旧版 LLM 客户端以符合 BaseLLMClient 接口"""
        class WrappedLLMClient(BaseLLMClient):
            provider_name = provider_name
            
            def __init__(self, inner_client):
                self._client = inner_client
            
            def generate_structured_output(self, prompt, pydantic_model, temperature=0.2):
                return self._client.generate_structured_output(prompt, pydantic_model, temperature)
            
            def health_check(self):
                return True
        
        return WrappedLLMClient(client)
    
    @classmethod
    def get_backup_llm_providers(cls) -> List[str]:
        """获取备用 LLM Provider 列表"""
        backup_str = settings.BACKUP_LLM_PROVIDERS
        return [p.strip() for p in backup_str.split(",") if p.strip()]
    
    # ========== Utility Methods ==========
    
    @classmethod
    def clear_cache(cls):
        """清除所有缓存的客户端实例"""
        cls._image_clients.clear()
        cls._video_clients.clear()
        cls._llm_clients.clear()
    
    # ========== TTS Clients ==========
    
    _tts_clients: Dict[str, Any] = {}
    
    @classmethod
    def get_tts_client(cls, provider: Optional[str] = None):
        """
        获取 TTS 语音合成客户端
        
        Args:
            provider: openai, doubao, aliyun, minimax, zhipu
        """
        provider = provider or settings.TTS_PROVIDER
        
        if provider not in cls._tts_clients:
            cls._tts_clients[provider] = cls._create_tts_client(provider)
        
        return cls._tts_clients[provider]
    
    @classmethod
    def _create_tts_client(cls, provider: str):
        """创建 TTS 客户端实例"""
        if provider == "openai":
            from integrations.tts_client import tts_client
            return tts_client
        elif provider == "doubao":
            from integrations.tts_doubao_client import doubao_tts_client
            return doubao_tts_client
        elif provider == "aliyun":
            from integrations.tts_aliyun_client import aliyun_tts_client
            return aliyun_tts_client
        elif provider == "minimax":
            from integrations.tts_minimax_client import minimax_tts_client
            return minimax_tts_client
        elif provider == "zhipu":
            from integrations.tts_zhipu_client import zhipu_tts_client
            return zhipu_tts_client
        else:
            raise ValueError(f"未知的 TTS Provider: {provider}")
    
    @classmethod
    def list_available_providers(cls) -> Dict[str, List[str]]:
        """列出所有可用的 Provider"""
        return {
            "image": ["google", "aliyun", "replicate"],
            "video": ["google", "replicate", "volcengine", "aliyun"],
            "llm": ["google", "doubao", "deepseek", "openai"],
            "tts": ["openai", "doubao", "aliyun", "minimax", "zhipu"]
        }
