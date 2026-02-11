"""
阿里云万相 (Wanx) 图像/视频生成客户端
使用 DashScope 官方 SDK
"""
import base64
import logging
import os
import time
from typing import Optional

# 在导入 dashscope 之前清除代理（国内服务不需要代理）
# 这必须在 import dashscope 之前执行，否则 SDK 会缓存代理设置
_original_proxies_for_dashscope = {}
for _key in ['HTTP_PROXY', 'HTTPS_PROXY', 'http_proxy', 'https_proxy']:
    _original_proxies_for_dashscope[_key] = os.environ.get(_key)
    if _key in os.environ:
        del os.environ[_key]

import dashscope
import requests
from dashscope import ImageSynthesis
from http import HTTPStatus

# 导入后恢复代理（供其他模块使用）
for _key, _value in _original_proxies_for_dashscope.items():
    if _value is not None:
        os.environ[_key] = _value

from config import settings
from integrations.base_client import BaseImageClient, BaseVideoClient, QuotaExceededError, AuthenticationError

logger = logging.getLogger(__name__)


def _disable_proxy_for_china():
    """国内 API 调用时禁用代理"""
    # 保存原始代理设置
    original_proxies = {
        'HTTP_PROXY': os.environ.get('HTTP_PROXY'),
        'HTTPS_PROXY': os.environ.get('HTTPS_PROXY'),
        'http_proxy': os.environ.get('http_proxy'),
        'https_proxy': os.environ.get('https_proxy'),
    }
    # 清除代理
    for key in ['HTTP_PROXY', 'HTTPS_PROXY', 'http_proxy', 'https_proxy']:
        if key in os.environ:
            del os.environ[key]
    return original_proxies


def _restore_proxy(original_proxies: dict):
    """恢复原始代理设置"""
    for key, value in original_proxies.items():
        if value is not None:
            os.environ[key] = value


class AliyunWanxImageClient(BaseImageClient):
    """阿里云万相图像生成客户端 (DashScope SDK)"""

    provider_name: str = "aliyun"

    def __init__(self):
        self.api_key = settings.DASHSCOPE_API_KEY
        self.model = settings.ALIYUN_WANX_MODEL or "wanx2.1-t2i-turbo"

        if self.api_key:
            dashscope.api_key = self.api_key
            # 禁用 DashScope SDK 的代理（国内服务不需要代理）
            try:
                dashscope.http_proxy = None
                dashscope.https_proxy = None
            except AttributeError:
                pass
        else:
            logger.warning("阿里云 DashScope API Key 未配置")

    def generate_image(
        self,
        prompt: str,
        reference_image_path: Optional[str] = None,
        style_preset: Optional[str] = None,
        negative_prompt: Optional[str] = None,
        seed: Optional[int] = None,
        **kwargs
    ) -> bytes:
        """使用万相生成图像

        Args:
            prompt: 主提示词
            reference_image_path: 参考图路径（可选）
            style_preset: 风格预设（可选）
            negative_prompt: 负面提示词，描述不想要的内容（可选）
            seed: 随机种子，用于复现结果（可选）
        """
        if not self.api_key:
            raise AuthenticationError("阿里云 DashScope API Key 未配置")

        # 构建完整 prompt
        full_prompt = prompt
        if style_preset:
            full_prompt = f"{prompt}, {style_preset}"

        # 国内 API 禁用代理
        original_proxies = _disable_proxy_for_china()

        try:
            # 构建调用参数
            call_params = {
                "api_key": self.api_key,
                "model": self.model,
                "prompt": full_prompt,
                "n": 1,
                "size": "1024*1024"
            }

            # 添加负面提示词（如果支持）
            if negative_prompt:
                call_params["negative_prompt"] = negative_prompt

            # 添加随机种子（如果支持）
            if seed is not None:
                call_params["seed"] = seed

            # 使用 SDK 调用
            rsp = ImageSynthesis.call(**call_params)

            if rsp.status_code == HTTPStatus.OK:
                # 获取图片 URL 并下载
                if rsp.output and rsp.output.results:
                    image_url = rsp.output.results[0].url
                    image_response = requests.get(image_url, timeout=30, proxies={})
                    return image_response.content
                else:
                    raise RuntimeError(f"阿里云万相返回结果为空: {rsp}")
            else:
                error_msg = f"阿里云万相生成失败: code={rsp.status_code}, message={rsp.message}"
                logger.error(error_msg)
                if rsp.status_code == 429:
                    raise QuotaExceededError("阿里云万相 API 限流")
                elif rsp.status_code in (401, 403):
                    raise AuthenticationError("阿里云认证失败")
                else:
                    raise RuntimeError(error_msg)

        except Exception as e:
            logger.error(f"阿里云万相图像生成失败: {e}")
            raise
        finally:
            _restore_proxy(original_proxies)

    def health_check(self) -> bool:
        return bool(self.api_key)


class AliyunWanxVideoClient(BaseVideoClient):
    """阿里云万相视频生成客户端 (DashScope HTTP API)

    使用 wanx2.1-i2v-turbo 模型进行图生视频
    文档: https://help.aliyun.com/zh/model-studio/developer-reference/image-to-video
    """

    provider_name: str = "aliyun"

    def __init__(self):
        self.api_key = settings.DASHSCOPE_API_KEY
        self.endpoint = "https://dashscope.aliyuncs.com/api/v1"
        # 图生视频模型: wanx2.1-i2v-turbo (快速) 或 wanx2.1-i2v-plus (高质量)
        self.model = "wanx2.1-i2v-turbo"

        if not self.api_key:
            logger.warning("阿里云 DashScope API Key 未配置")

    def _get_oss_upload_policy(self) -> dict:
        """获取 OSS 上传凭证"""
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        response = requests.post(
            f"{self.endpoint}/uploads/policies",
            headers=headers,
            json={"model": self.model, "action": "image2video"},
            timeout=30
        )

        if response.status_code == 200:
            return response.json().get("data", {})
        else:
            logger.error(f"获取上传凭证失败: {response.status_code} - {response.text}")
            return {}

    def _upload_image_to_oss(self, image_path: str) -> str:
        """上传图片到阿里云 OSS 并返回 URL

        DashScope 图生视频 API 需要一个可访问的 HTTP URL，
        需要先将本地图片上传
        """
        # 方法1: 使用阿里云 OSS SDK 上传 (推荐，最可靠)
        if settings.ALIYUN_ACCESS_KEY_ID and settings.ALIYUN_ACCESS_KEY_SECRET and settings.ALIYUN_OSS_BUCKET:
            try:
                import oss2
                import uuid as uuid_module

                auth = oss2.Auth(settings.ALIYUN_ACCESS_KEY_ID, settings.ALIYUN_ACCESS_KEY_SECRET)
                bucket = oss2.Bucket(auth, settings.ALIYUN_OSS_ENDPOINT, settings.ALIYUN_OSS_BUCKET)

                # 生成唯一的对象名
                ext = os.path.splitext(image_path)[1] or '.png'
                object_name = f"animematrix/uploads/{uuid_module.uuid4().hex}{ext}"

                # 上传文件
                with open(image_path, 'rb') as f:
                    bucket.put_object(object_name, f)

                # 构建公开访问 URL
                # 格式: https://{bucket}.{endpoint}/{object_name}
                endpoint = settings.ALIYUN_OSS_ENDPOINT
                if endpoint.startswith('http://') or endpoint.startswith('https://'):
                    # 已经包含协议
                    base_url = endpoint.replace('http://', f'http://{settings.ALIYUN_OSS_BUCKET}.').replace('https://', f'https://{settings.ALIYUN_OSS_BUCKET}.')
                else:
                    base_url = f"https://{settings.ALIYUN_OSS_BUCKET}.{endpoint}"

                oss_url = f"{base_url}/{object_name}"
                logger.info(f"图片上传成功 (OSS): {oss_url}")
                return oss_url

            except ImportError:
                logger.warning("oss2 模块未安装，请运行: pip install oss2")
            except Exception as e:
                logger.warning(f"OSS 上传失败: {type(e).__name__}: {e}")
        else:
            logger.info("OSS 配置不完整，尝试其他上传方式")

        # 方法2: 使用 dashscope SDK 的 File.upload()
        try:
            from dashscope.common.file import File
            # File.upload 返回 oss:// 格式的 URL，DashScope API 可以直接使用
            result = File.upload(
                file_path=image_path,
                api_key=self.api_key
            )
            if result and hasattr(result, 'file_url') and result.file_url:
                logger.info(f"图片上传成功 (File.upload): {result.file_url[:80]}...")
                return result.file_url
            elif result and isinstance(result, str):
                logger.info(f"图片上传成功 (File.upload): {result[:80]}...")
                return result
            else:
                logger.warning(f"File.upload 返回结果异常: {result}")
        except ImportError:
            logger.warning("dashscope.common.file.File 不可用")
        except Exception as e:
            logger.warning(f"File.upload 失败: {type(e).__name__}: {e}")

        # 方法3: 使用 dashscope.upload_file() (某些版本)
        try:
            upload_url = dashscope.upload_file(
                file_path=image_path,
                api_key=self.api_key
            )
            if upload_url:
                logger.info(f"图片上传成功 (upload_file): {upload_url[:80]}...")
                return upload_url
        except AttributeError:
            logger.warning("dashscope.upload_file 不可用")
        except Exception as e:
            logger.warning(f"dashscope.upload_file 失败: {e}")

        # 所有方法都失败
        raise RuntimeError(
            "无法上传图片到 OSS。请配置以下环境变量:\n"
            "  ALIYUN_ACCESS_KEY_ID=你的AccessKeyId\n"
            "  ALIYUN_ACCESS_KEY_SECRET=你的AccessKeySecret\n"
            "  ALIYUN_OSS_BUCKET=你的Bucket名称\n"
            "  ALIYUN_OSS_ENDPOINT=oss-cn-shanghai.aliyuncs.com (根据你的区域)"
        )

    def _upload_to_dashscope(self, image_path: str) -> str:
        """使用 DashScope 文件服务上传图片

        DashScope 图生视频 API 需要使用其自己的文件服务上传的 URL
        """
        # 方法1: 使用 dashscope SDK 的 File.upload()
        try:
            from dashscope.common.file import File
            result = File.upload(
                file_path=image_path,
                api_key=self.api_key
            )
            if result and hasattr(result, 'file_url') and result.file_url:
                logger.info(f"DashScope 上传成功: {result.file_url[:80]}...")
                return result.file_url
            elif result and isinstance(result, str):
                logger.info(f"DashScope 上传成功: {result[:80]}...")
                return result
            else:
                logger.warning(f"File.upload 返回结果异常: {result}")
        except ImportError:
            logger.warning("dashscope.common.file.File 不可用")
        except Exception as e:
            logger.warning(f"File.upload 失败: {type(e).__name__}: {e}")

        # 方法2: 使用 dashscope.upload_file()
        try:
            upload_url = dashscope.upload_file(
                file_path=image_path,
                api_key=self.api_key
            )
            if upload_url:
                logger.info(f"DashScope upload_file 成功: {upload_url[:80]}...")
                return upload_url
        except AttributeError:
            logger.warning("dashscope.upload_file 不可用")
        except Exception as e:
            logger.warning(f"dashscope.upload_file 失败: {e}")

        raise RuntimeError("无法上传图片到 DashScope 文件服务")

    def generate_video(
        self,
        image_path: str,
        motion_prompt: Optional[str] = None,
        duration: float = 4.0,
        image_url: Optional[str] = None,
        **kwargs
    ) -> bytes:
        """使用万相图生视频 (DashScope SDK)

        Args:
            image_path: 输入图片路径（如果没有 image_url）
            motion_prompt: 运动描述提示词
            duration: 视频时长（秒），wanx2.1-i2v 固定生成约 5 秒视频
            image_url: 图片的 OSS URL（优先使用）

        Returns:
            视频文件的二进制数据
        """
        if not self.api_key:
            raise AuthenticationError("阿里云 DashScope API Key 未配置")

        from dashscope import VideoSynthesis

        # 国内 API/OSS 禁用代理（必须在所有网络请求之前）
        original_proxies = _disable_proxy_for_china()
        temp_file = None

        try:
            # 确定图片来源
            # 如果有外部 URL，需要下载到本地临时文件
            local_image_path = image_path

            if image_url and (not image_path or not os.path.exists(image_path)):
                logger.info(f"从 URL 下载图片: {image_url[:60]}...")
                import tempfile
                img_response = requests.get(image_url, timeout=30, proxies={})
                img_response.raise_for_status()
                temp_file = tempfile.NamedTemporaryFile(suffix='.png', delete=False)
                temp_file.write(img_response.content)
                temp_file.close()
                local_image_path = temp_file.name

            if not local_image_path or not os.path.exists(local_image_path):
                raise FileNotFoundError(f"图片文件不存在: {local_image_path}")

            # 构建提示词
            prompt = motion_prompt or "smooth camera movement, cinematic animation, high quality"

            logger.info(f"开始阿里云图生视频 (SDK): model={self.model}")

            # 使用 DashScope SDK 调用
            # SDK 会自动处理文件上传
            rsp = VideoSynthesis.call(
                model=self.model,
                prompt=prompt,
                img_url=f"file://{local_image_path}",  # 使用 file:// 协议让 SDK 自动上传
                api_key=self.api_key
            )

            logger.info(f"VideoSynthesis.call 返回: status={rsp.status_code}")

            if rsp.status_code == HTTPStatus.OK:
                # 获取视频 URL
                output = rsp.output
                video_url = None

                if hasattr(output, 'video_url'):
                    video_url = output.video_url
                elif isinstance(output, dict):
                    video_url = output.get('video_url')

                if video_url:
                    logger.info(f"视频生成成功，正在下载: {video_url[:80]}...")
                    video_response = requests.get(video_url, timeout=120, proxies={})
                    video_response.raise_for_status()
                    logger.info(f"视频下载完成，大小: {len(video_response.content)} bytes")
                    return video_response.content
                else:
                    logger.error(f"无法从响应中获取视频 URL: {output}")
                    raise RuntimeError(f"视频生成成功但无法获取 URL: {output}")
            else:
                error_msg = f"阿里云视频生成失败: code={rsp.status_code}, message={rsp.message}"
                logger.error(error_msg)
                if rsp.status_code == 429:
                    raise QuotaExceededError("阿里云万相视频 API 限流")
                elif rsp.status_code in (401, 403):
                    raise AuthenticationError("阿里云认证失败")
                else:
                    raise RuntimeError(error_msg)

        except QuotaExceededError:
            raise
        except AuthenticationError:
            raise
        except RuntimeError:
            raise
        except Exception as e:
            logger.error(f"阿里云视频生成异常: {type(e).__name__}: {e}")
            raise RuntimeError(f"阿里云视频生成失败: {e}")
        finally:
            _restore_proxy(original_proxies)
            # 清理临时文件
            if temp_file and os.path.exists(temp_file.name):
                try:
                    os.unlink(temp_file.name)
                except:
                    pass

    def health_check(self) -> bool:
        return bool(self.api_key)


# 单例实例
aliyun_image_client = AliyunWanxImageClient()
aliyun_video_client = AliyunWanxVideoClient()
