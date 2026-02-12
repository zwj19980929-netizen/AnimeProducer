"""
阿里云 OSS 上传服务

用于将生成的图片、视频、音频直接上传到 OSS，避免占用本地存储空间
"""
import logging
import os
import uuid
from typing import Optional, Tuple

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
            # 禁用代理，阿里云 OSS 是国内服务
            auth = oss2.Auth(self.access_key_id, self.access_key_secret)
            # 创建 Session 并显式禁用代理
            session = oss2.Session()
            session.session.trust_env = False  # 不读取系统代理
            self._bucket = oss2.Bucket(auth, self.endpoint, self.bucket_name, session=session)
        return self._bucket

    def _build_url(self, object_name: str) -> str:
        """构建公开访问 URL"""
        endpoint = self.endpoint
        if endpoint.startswith('http://') or endpoint.startswith('https://'):
            base_url = endpoint.replace('http://', f'http://{self.bucket_name}.').replace('https://', f'https://{self.bucket_name}.')
        else:
            base_url = f"https://{self.bucket_name}.{endpoint}"
        return f"{base_url}/{object_name}"

    def upload_bytes(
        self,
        data: bytes,
        filename: Optional[str] = None,
        ext: str = ".png",
        folder: str = "uploads"
    ) -> str:
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

            oss_url = self._build_url(object_name)
            logger.info(f"文件上传成功: {oss_url}")
            return oss_url

        finally:
            _restore_proxy(original_proxies)

    def upload_image_bytes(self, image_data: bytes, filename: Optional[str] = None, ext: str = ".png") -> str:
        """上传图片到 OSS"""
        return self.upload_bytes(image_data, filename, ext, folder="keyframes")

    def upload_video_bytes(self, video_data: bytes, filename: Optional[str] = None, ext: str = ".mp4") -> str:
        """上传视频到 OSS"""
        return self.upload_bytes(video_data, filename, ext, folder="videos")

    def upload_audio_bytes(self, audio_data: bytes, filename: Optional[str] = None, ext: str = ".mp3") -> str:
        """上传音频到 OSS"""
        return self.upload_bytes(audio_data, filename, ext, folder="audio")

    def upload_file(self, file_path: str, folder: Optional[str] = None) -> str:
        """
        上传本地文件到 OSS

        Args:
            file_path: 本地文件路径
            folder: OSS 中的文件夹（可选，默认根据文件类型自动选择）

        Returns:
            文件的公开访问 URL
        """
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"文件不存在: {file_path}")

        with open(file_path, 'rb') as f:
            data = f.read()

        ext = os.path.splitext(file_path)[1].lower() or '.bin'
        filename = os.path.splitext(os.path.basename(file_path))[0]

        # 根据扩展名自动选择文件夹
        if folder is None:
            if ext in ['.png', '.jpg', '.jpeg', '.webp', '.gif']:
                folder = "keyframes"
            elif ext in ['.mp4', '.mov', '.avi', '.webm']:
                folder = "videos"
            elif ext in ['.mp3', '.wav', '.ogg', '.flac', '.aac']:
                folder = "audio"
            else:
                folder = "uploads"

        return self.upload_bytes(data, filename=filename, ext=ext, folder=folder)

    def upload_file_and_cleanup(self, file_path: str, folder: Optional[str] = None) -> str:
        """
        上传本地文件到 OSS 并删除本地文件

        Args:
            file_path: 本地文件路径
            folder: OSS 中的文件夹

        Returns:
            文件的公开访问 URL
        """
        url = self.upload_file(file_path, folder)

        # 删除本地文件
        try:
            os.remove(file_path)
            logger.debug(f"已删除本地文件: {file_path}")
        except Exception as e:
            logger.warning(f"删除本地文件失败: {file_path}, 错误: {e}")

        return url

    def download_to_temp(self, oss_url: str) -> str:
        """
        从 OSS 下载文件到临时目录

        Args:
            oss_url: OSS 文件 URL

        Returns:
            本地临时文件路径
        """
        import tempfile
        import requests

        # 获取文件扩展名
        ext = os.path.splitext(oss_url)[1] or '.bin'

        # 下载文件
        response = requests.get(oss_url, timeout=60)
        response.raise_for_status()

        # 保存到临时文件
        temp_file = tempfile.NamedTemporaryFile(suffix=ext, delete=False)
        temp_file.write(response.content)
        temp_file.close()

        logger.debug(f"下载文件到临时目录: {temp_file.name}")
        return temp_file.name


# 便捷函数
def upload_image_to_oss(image_data: bytes, filename: Optional[str] = None) -> str:
    """上传图片到 OSS 的便捷函数"""
    return OSSService.get_instance().upload_image_bytes(image_data, filename)


def upload_video_to_oss(video_data: bytes, filename: Optional[str] = None) -> str:
    """上传视频到 OSS 的便捷函数"""
    return OSSService.get_instance().upload_video_bytes(video_data, filename)


def upload_audio_to_oss(audio_data: bytes, filename: Optional[str] = None, ext: str = ".mp3") -> str:
    """上传音频到 OSS 的便捷函数"""
    return OSSService.get_instance().upload_audio_bytes(audio_data, filename, ext)


def upload_file_to_oss(file_path: str, cleanup: bool = True) -> str:
    """
    上传本地文件到 OSS 的便捷函数

    Args:
        file_path: 本地文件路径
        cleanup: 是否删除本地文件，默认 True

    Returns:
        OSS URL
    """
    if cleanup:
        return OSSService.get_instance().upload_file_and_cleanup(file_path)
    else:
        return OSSService.get_instance().upload_file(file_path)


def is_oss_configured() -> bool:
    """检查 OSS 是否已配置"""
    return OSSService.get_instance().is_configured()


def require_oss() -> OSSService:
    """
    获取 OSS 服务实例，如果未配置则抛出异常

    Returns:
        OSSService 实例

    Raises:
        RuntimeError: OSS 未配置
    """
    oss = OSSService.get_instance()
    if not oss.is_configured():
        raise RuntimeError(
            "OSS 未配置，所有资源必须上传到 OSS。请在 .env 中设置:\n"
            "  ALIYUN_ACCESS_KEY_ID=你的AccessKeyId\n"
            "  ALIYUN_ACCESS_KEY_SECRET=你的AccessKeySecret\n"
            "  ALIYUN_OSS_BUCKET=你的Bucket名称\n"
            "  ALIYUN_OSS_ENDPOINT=oss-cn-shanghai.aliyuncs.com"
        )
    return oss
