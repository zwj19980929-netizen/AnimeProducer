"""
阿里云万相 (Wanx) 图像/视频生成客户端
"""
import base64
import json
import logging
import time
from typing import Optional
import requests

from config import settings
from integrations.base_client import BaseImageClient, BaseVideoClient, QuotaExceededError, AuthenticationError

logger = logging.getLogger(__name__)


class AliyunWanxImageClient(BaseImageClient):
    """阿里云万相图像生成客户端"""
    
    provider_name: str = "aliyun"
    
    def __init__(self):
        self.access_key_id = settings.ALIYUN_ACCESS_KEY_ID
        self.access_key_secret = settings.ALIYUN_ACCESS_KEY_SECRET
        self.region = settings.ALIYUN_REGION
        self.model = settings.ALIYUN_WANX_MODEL
        self.endpoint = f"https://dashscope.aliyuncs.com/api/v1"
        
        if not self.access_key_id:
            logger.warning("阿里云 Access Key 未配置")
    
    def generate_image(
        self,
        prompt: str,
        reference_image_path: Optional[str] = None,
        style_preset: Optional[str] = None,
        **kwargs
    ) -> bytes:
        """使用万相生成图像"""
        if not self.access_key_id:
            raise AuthenticationError("阿里云 Access Key 未配置")
        
        headers = {
            "Authorization": f"Bearer {self.access_key_id}",
            "Content-Type": "application/json",
            "X-DashScope-Async": "enable"
        }
        
        # 构建完整 prompt
        full_prompt = prompt
        if style_preset:
            full_prompt = f"{prompt}, {style_preset}"
        
        payload = {
            "model": self.model,
            "input": {
                "prompt": full_prompt
            },
            "parameters": {
                "size": "1024*1024",
                "n": 1
            }
        }
        
        # 如果有参考图，添加到请求中
        if reference_image_path:
            with open(reference_image_path, "rb") as f:
                ref_b64 = base64.b64encode(f.read()).decode("utf-8")
            payload["input"]["ref_img"] = f"data:image/png;base64,{ref_b64}"
        
        try:
            # 提交任务
            response = requests.post(
                f"{self.endpoint}/services/aigc/text2image/image-synthesis",
                headers=headers,
                json=payload,
                timeout=30
            )
            
            if response.status_code == 429:
                raise QuotaExceededError("阿里云万相 API 限流")
            if response.status_code in (401, 403):
                raise AuthenticationError("阿里云认证失败")
            
            response.raise_for_status()
            result = response.json()
            
            task_id = result.get("output", {}).get("task_id")
            if not task_id:
                raise RuntimeError(f"阿里云万相任务创建失败: {result}")
            
            # 轮询任务状态
            for _ in range(60):
                status_response = requests.get(
                    f"{self.endpoint}/tasks/{task_id}",
                    headers=headers,
                    timeout=10
                )
                status_data = status_response.json()
                task_status = status_data.get("output", {}).get("task_status")
                
                if task_status == "SUCCEEDED":
                    image_url = status_data["output"]["results"][0]["url"]
                    image_response = requests.get(image_url, timeout=30)
                    return image_response.content
                elif task_status == "FAILED":
                    raise RuntimeError(f"阿里云万相生成失败: {status_data}")
                
                time.sleep(2)
            
            raise RuntimeError("阿里云万相任务超时")
            
        except requests.exceptions.RequestException as e:
            logger.error(f"阿里云万相 API 请求失败: {e}")
            raise
    
    def health_check(self) -> bool:
        return bool(self.access_key_id)


class AliyunWanxVideoClient(BaseVideoClient):
    """阿里云万相视频生成客户端"""
    
    provider_name: str = "aliyun"
    
    def __init__(self):
        self.access_key_id = settings.ALIYUN_ACCESS_KEY_ID
        self.access_key_secret = settings.ALIYUN_ACCESS_KEY_SECRET
        self.endpoint = f"https://dashscope.aliyuncs.com/api/v1"
        
        if not self.access_key_id:
            logger.warning("阿里云 Access Key 未配置")
    
    def generate_video(
        self,
        image_path: str,
        motion_prompt: Optional[str] = None,
        duration: float = 4.0,
        **kwargs
    ) -> bytes:
        """使用万相图生视频"""
        if not self.access_key_id:
            raise AuthenticationError("阿里云 Access Key 未配置")
        
        headers = {
            "Authorization": f"Bearer {self.access_key_id}",
            "Content-Type": "application/json",
            "X-DashScope-Async": "enable"
        }
        
        # 读取图片
        with open(image_path, "rb") as f:
            image_b64 = base64.b64encode(f.read()).decode("utf-8")
        
        payload = {
            "model": "wanx-v1",
            "input": {
                "image_url": f"data:image/png;base64,{image_b64}",
                "prompt": motion_prompt or "smooth camera movement, high quality animation"
            },
            "parameters": {
                "duration": int(duration)
            }
        }
        
        try:
            response = requests.post(
                f"{self.endpoint}/services/aigc/image2video/video-synthesis",
                headers=headers,
                json=payload,
                timeout=30
            )
            
            if response.status_code == 429:
                raise QuotaExceededError("阿里云万相视频 API 限流")
            if response.status_code in (401, 403):
                raise AuthenticationError("阿里云认证失败")
            
            response.raise_for_status()
            result = response.json()
            
            task_id = result.get("output", {}).get("task_id")
            if not task_id:
                raise RuntimeError(f"阿里云视频任务创建失败: {result}")
            
            # 轮询任务状态
            for _ in range(120):
                status_response = requests.get(
                    f"{self.endpoint}/tasks/{task_id}",
                    headers=headers,
                    timeout=10
                )
                status_data = status_response.json()
                task_status = status_data.get("output", {}).get("task_status")
                
                if task_status == "SUCCEEDED":
                    video_url = status_data["output"]["video_url"]
                    video_response = requests.get(video_url, timeout=60)
                    return video_response.content
                elif task_status == "FAILED":
                    raise RuntimeError(f"阿里云视频生成失败: {status_data}")
                
                time.sleep(2)
            
            raise RuntimeError("阿里云视频任务超时")
            
        except requests.exceptions.RequestException as e:
            logger.error(f"阿里云视频 API 请求失败: {e}")
            raise
    
    def health_check(self) -> bool:
        return bool(self.access_key_id)


aliyun_image_client = AliyunWanxImageClient()
aliyun_video_client = AliyunWanxVideoClient()
