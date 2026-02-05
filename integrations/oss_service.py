"""
阿里云 OSS 上传服务

用于将生成的图片直接上传到 OSS，避免占用本地存储空间
"""
import logging
import os
import uuid
from typing import Optional

from config import settings

logger = logging.getLogger(__name__)


def _disable_proxy_for_china():
    """国内 API 调用时禁用代理"""
    original_proxies = {
        'HTTP_PROXY': os.environ.get('HTTP_PROXY'),
        'HTTPS_PROXY': os.environ.get('HTTPS_PROXY'),
        'http_proxy': os.environ.get('http_proxy'),
        'https_proxy': os.environ.get('https_proxy'),
    }
    for key in ['HTTP_PROXY', 'HTTPS_PROXY', 'http_proxy', 'https_proxy']:
        if key in os.environ:
            del os.environ[key]
    return original_proxies


def _restore_proxy(original_proxies: dict):
    """恢复原始代理设置"""
    for key, value in original_proxies.items():
        if value is not None:
            os.environ[key] = value


class OSSService:
    """阿里云 OSS 服务"""

    _instance: Optional["OSSService"] = None

    def __init__(self):
        self.access_key_id = settings.ALIYUN_ACCESS_KEY_ID
        self.access_key_secret = settings.ALIYUN_ACCESS_KEY_SECRET
        self.bucket_name = settings.ALIYUN_OSS_BUCKET
        self.endpoint = settings.ALIYUN_OSS_ENDPOINT
        self._bucket = None

    @classmethod
    def get_instance(cls) -> "OSSService":
        """获取单例实例"""
        if cls._instance is None:
            cls._instance = OSSService()
        return cls._instance

    def is_configured(self) -> bool:
        """检查 OSS 是否已配置"""
        return bool(
            self.access_key_id and
            self.access_key_secret and
            self.bucket_name and
            self.endpoint
        )

    def _get_bucket(self):
        """获取 OSS Bucket 对象"""
        if self._bucket is None:
            if not self.is_configured():
                raise RuntimeError(
                    "OSS 未配置。请在 .env 中设置:\n"
                    "  ALIYUN_ACCESS_KEY_ID=你的AccessKeyId\n"
                    "  ALIYUN_ACCESS_KEY_SECRET=你的AccessKeySecret\n"
                    "  ALIYUN_OSS_BUCKET=你的Bucket名称\n"
                    "  ALIYUN_OSS_ENDPOINT=oss-cn-shanghai.aliyuncs.com"
                )
            import oss2
            auth = oss2.Auth(self.access_key_id, self.access_key_secret)
            self._bucket = oss2.Bucket(auth, self.endpoint, self.bucket_name)
        return self._bucket

    def upload_bytes(self, data: bytes, filename: Optional[str] = None, ext: str = ".png", folder: str = "uploads") -> str:
        """
        上传字节数据到 OSS

        Args:
            data: 二进制数据
            filename: 可选的文件名（不含扩展名）
            ext: 文件扩展名，默认 .png
            folder: OSS 中的文件夹，默认 uploads

        Returns:
            文件的公开访问 URL
        """
        if not self.is_configured():
            raise RuntimeError("OSS 未配置，无法上传")

        original_proxies = _disable_proxy_for_china()
        try:
            bucket = self._get_bucket()

            # 生成对象名
            if filename:
                object_name = f"animematrix/{folder}/{filename}{ext}"
            else:
                object_name = f"animematrix/{folder}/{uuid.uuid4().hex}{ext}"

            # 上传
            bucket.put_object(object_name, data)

            # 构建公开访问 URL
            endpoint = self.endpoint
            if endpoint.startswith('http://') or endpoint.startswith('https://'):
                base_url = endpoint.replace('http://', f'http://{self.bucket_name}.').replace('https://', f'https://{self.bucket_name}.')
            else:
                base_url = f"https://{self.bucket_name}.{endpoint}"

            oss_url = f"{base_url}/{object_name}"
            logger.info(f"文件上传成功: {oss_url}")
            return oss_url

        finally:
            _restore_proxy(original_proxies)

    def upload_image_bytes(self, image_data: bytes, filename: Optional[str] = None, ext: str = ".png") -> str:
        """上传图片到 OSS（兼容旧接口）"""
        return self.upload_bytes(image_data, filename, ext, folder="keyframes")

    def upload_video_bytes(self, video_data: bytes, filename: Optional[str] = None, ext: str = ".mp4") -> str:
        """上传视频到 OSS"""
        return self.upload_bytes(video_data, filename, ext, folder="videos")

    def upload_file(self, file_path: str) -> str:
        """
        上传本地文件到 OSS

        Args:
            file_path: 本地文件路径

        Returns:
            文件的公开访问 URL
        """
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"文件不存在: {file_path}")

        with open(file_path, 'rb') as f:
            data = f.read()

        ext = os.path.splitext(file_path)[1] or '.png'
        filename = os.path.splitext(os.path.basename(file_path))[0]
        return self.upload_image_bytes(data, filename=filename, ext=ext)


# 便捷函数
def upload_image_to_oss(image_data: bytes, filename: Optional[str] = None) -> str:
    """上传图片到 OSS 的便捷函数"""
    return OSSService.get_instance().upload_image_bytes(image_data, filename)


def is_oss_configured() -> bool:
    """检查 OSS 是否已配置"""
    return OSSService.get_instance().is_configured()
