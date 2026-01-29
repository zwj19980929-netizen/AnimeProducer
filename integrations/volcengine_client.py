"""
火山引擎视频生成客户端
支持字节跳动的视频生成 API
"""
import base64
import hashlib
import hmac
import json
import logging
import time
from datetime import datetime
from typing import Optional

import requests

from config import settings
from integrations.base_client import BaseVideoClient, QuotaExceededError, AuthenticationError

logger = logging.getLogger(__name__)


class VolcEngineVideoClient(BaseVideoClient):
    """火山引擎视频生成客户端"""
    
    provider_name: str = "volcengine"
    
    def __init__(self):
        self.access_key = settings.VOLCENGINE_ACCESS_KEY
        self.secret_key = settings.VOLCENGINE_SECRET_KEY
        self.region = settings.VOLCENGINE_REGION
        self.service = "cv"
        self.host = "visual.volcengineapi.com"
        
        if not self.access_key or not self.secret_key:
            logger.warning("火山引擎 Access Key 未配置")
    
    def _sign_request(self, method: str, path: str, params: dict, body: str = "") -> dict:
        """生成火山引擎 API 签名"""
        timestamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
        date = timestamp[:8]
        
        # 规范请求
        sorted_params = "&".join(f"{k}={v}" for k, v in sorted(params.items()))
        canonical_request = f"{method}\n{path}\n{sorted_params}\nhost:{self.host}\n\nhost\n{hashlib.sha256(body.encode()).hexdigest()}"
        
        # 待签名字符串
        credential_scope = f"{date}/{self.region}/{self.service}/request"
        string_to_sign = f"HMAC-SHA256\n{timestamp}\n{credential_scope}\n{hashlib.sha256(canonical_request.encode()).hexdigest()}"
        
        # 计算签名
        def sign(key, msg):
            return hmac.new(key, msg.encode(), hashlib.sha256).digest()
        
        k_date = sign(self.secret_key.encode(), date)
        k_region = sign(k_date, self.region)
        k_service = sign(k_region, self.service)
        k_signing = sign(k_service, "request")
        signature = hmac.new(k_signing, string_to_sign.encode(), hashlib.sha256).hexdigest()
        
        authorization = f"HMAC-SHA256 Credential={self.access_key}/{credential_scope}, SignedHeaders=host, Signature={signature}"
        
        return {
            "Host": self.host,
            "X-Date": timestamp,
            "Authorization": authorization,
            "Content-Type": "application/json"
        }
    
    def generate_video(
        self,
        image_path: str,
        motion_prompt: Optional[str] = None,
        duration: float = 4.0,
        **kwargs
    ) -> bytes:
        """使用火山引擎生成视频"""
        if not self.access_key or not self.secret_key:
            raise AuthenticationError("火山引擎 Access Key 未配置")
        
        # 读取图片并编码
        with open(image_path, "rb") as f:
            image_b64 = base64.b64encode(f.read()).decode("utf-8")
        
        # 构建请求
        path = "/v1/video/generate"
        params = {"Action": "CVProcess", "Version": "2022-08-31"}
        
        body = json.dumps({
            "req_key": "img2video",
            "binary_data_base64": [image_b64],
            "prompt": motion_prompt or "smooth animation, high quality",
            "duration": int(duration)
        })
        
        headers = self._sign_request("POST", path, params, body)
        
        try:
            response = requests.post(
                f"https://{self.host}{path}",
                params=params,
                headers=headers,
                data=body,
                timeout=120
            )
            
            if response.status_code == 429:
                raise QuotaExceededError("火山引擎 API 限流")
            if response.status_code in (401, 403):
                raise AuthenticationError("火山引擎认证失败")
            
            response.raise_for_status()
            result = response.json()
            
            if result.get("code") != 0:
                raise RuntimeError(f"火山引擎 API 错误: {result.get('message')}")
            
            # 获取视频 URL 并下载
            video_url = result.get("data", {}).get("video_url")
            if video_url:
                video_response = requests.get(video_url, timeout=60)
                return video_response.content
            
            # 或者直接返回 base64 数据
            video_b64 = result.get("data", {}).get("binary_data_base64", [None])[0]
            if video_b64:
                return base64.b64decode(video_b64)
            
            raise RuntimeError("火山引擎未返回视频数据")
            
        except requests.exceptions.RequestException as e:
            logger.error(f"火山引擎 API 请求失败: {e}")
            raise
    
    def health_check(self) -> bool:
        """检查 API 是否可用"""
        return bool(self.access_key and self.secret_key)


volcengine_video_client = VolcEngineVideoClient()
