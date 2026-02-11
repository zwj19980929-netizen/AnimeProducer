"""
Rate Limiter and Failover - API 限流与故障转移模块

提供：
1. 令牌桶限流器 - 控制 API 调用频率
2. 智能故障转移 - 自动切换到备用 Provider
3. 配额管理 - 跟踪和管理 API 配额
4. 熔断器 - 防止雪崩效应
"""

import logging
import threading
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from functools import wraps
from typing import Any, Callable, Dict, List, Optional, Type

from core.errors import (
    ExternalAPIError,
    RateLimitError,
    TransientError,
)

logger = logging.getLogger(__name__)


# ============================================================================
# Token Bucket Rate Limiter
# ============================================================================


class TokenBucketLimiter:
    """
    令牌桶限流器

    控制 API 调用频率，防止触发外部服务的限流。
    """

    def __init__(
        self,
        rate: float,  # 每秒生成的令牌数
        capacity: int,  # 桶容量
        name: str = "default"
    ):
        self.rate = rate
        self.capacity = capacity
        self.name = name
        self.tokens = capacity
        self.last_update = time.time()
        self._lock = threading.Lock()

    def acquire(self, tokens: int = 1, timeout: float = 30.0) -> bool:
        """
        获取令牌

        Args:
            tokens: 需要的令牌数
            timeout: 最大等待时间

        Returns:
            bool: 是否成功获取令牌
        """
        start_time = time.time()

        while True:
            with self._lock:
                self._refill()

                if self.tokens >= tokens:
                    self.tokens -= tokens
                    return True

            # 检查超时
            elapsed = time.time() - start_time
            if elapsed >= timeout:
                logger.warning(f"[{self.name}] Rate limit timeout after {elapsed:.1f}s")
                return False

            # 计算需要等待的时间
            wait_time = min((tokens - self.tokens) / self.rate, timeout - elapsed)
            if wait_time > 0:
                time.sleep(wait_time)

    def _refill(self):
        """补充令牌"""
        now = time.time()
        elapsed = now - self.last_update
        self.tokens = min(self.capacity, self.tokens + elapsed * self.rate)
        self.last_update = now


class RateLimiterRegistry:
    """限流器注册表"""

    _limiters: Dict[str, TokenBucketLimiter] = {}
    _lock = threading.Lock()

    # 默认限流配置（每分钟请求数）
    DEFAULT_LIMITS = {
        "google_imagen": (10, 20),      # 10 req/s, burst 20
        "google_veo": (5, 10),          # 5 req/s, burst 10
        "google_gemini": (60, 100),     # 60 req/s, burst 100
        "aliyun_wanx": (5, 10),
        "volcengine": (5, 10),
        "replicate": (10, 20),
        "openai_tts": (50, 100),
        "fal": (10, 20),
        "default": (10, 20),
    }

    @classmethod
    def get_limiter(cls, name: str) -> TokenBucketLimiter:
        """获取或创建限流器"""
        with cls._lock:
            if name not in cls._limiters:
                rate, capacity = cls.DEFAULT_LIMITS.get(name, cls.DEFAULT_LIMITS["default"])
                cls._limiters[name] = TokenBucketLimiter(rate, capacity, name)
            return cls._limiters[name]

    @classmethod
    def configure(cls, name: str, rate: float, capacity: int):
        """配置限流器"""
        with cls._lock:
            cls._limiters[name] = TokenBucketLimiter(rate, capacity, name)


def rate_limited(limiter_name: str, tokens: int = 1, timeout: float = 30.0):
    """
    限流装饰器

    Args:
        limiter_name: 限流器名称
        tokens: 每次调用消耗的令牌数
        timeout: 最大等待时间
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            limiter = RateLimiterRegistry.get_limiter(limiter_name)
            if not limiter.acquire(tokens, timeout):
                raise RateLimitError(limiter_name, retry_after=int(timeout))
            return func(*args, **kwargs)

        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            import asyncio
            limiter = RateLimiterRegistry.get_limiter(limiter_name)
            # 异步版本使用非阻塞等待
            start_time = time.time()
            while not limiter.acquire(tokens, timeout=0.1):
                if time.time() - start_time >= timeout:
                    raise RateLimitError(limiter_name, retry_after=int(timeout))
                await asyncio.sleep(0.1)
            return await func(*args, **kwargs)

        import asyncio
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return wrapper

    return decorator


# ============================================================================
# Circuit Breaker
# ============================================================================


class CircuitState(str, Enum):
    """熔断器状态"""
    CLOSED = "closed"      # 正常状态
    OPEN = "open"          # 熔断状态
    HALF_OPEN = "half_open"  # 半开状态（尝试恢复）


@dataclass
class CircuitBreaker:
    """
    熔断器

    当错误率超过阈值时自动熔断，防止雪崩效应。
    """
    name: str
    failure_threshold: int = 5  # 触发熔断的连续失败次数
    recovery_timeout: float = 60.0  # 熔断后恢复尝试的等待时间
    half_open_max_calls: int = 3  # 半开状态允许的最大调用次数

    state: CircuitState = field(default=CircuitState.CLOSED)
    failure_count: int = field(default=0)
    success_count: int = field(default=0)
    last_failure_time: Optional[datetime] = field(default=None)
    half_open_calls: int = field(default=0)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def can_execute(self) -> bool:
        """检查是否可以执行"""
        with self._lock:
            if self.state == CircuitState.CLOSED:
                return True

            if self.state == CircuitState.OPEN:
                # 检查是否可以尝试恢复
                if self.last_failure_time:
                    elapsed = (datetime.now() - self.last_failure_time).total_seconds()
                    if elapsed >= self.recovery_timeout:
                        self.state = CircuitState.HALF_OPEN
                        self.half_open_calls = 0
                        logger.info(f"[{self.name}] Circuit breaker entering half-open state")
                        return True
                return False

            if self.state == CircuitState.HALF_OPEN:
                if self.half_open_calls < self.half_open_max_calls:
                    self.half_open_calls += 1
                    return True
                return False

            return False

    def record_success(self):
        """记录成功"""
        with self._lock:
            if self.state == CircuitState.HALF_OPEN:
                self.success_count += 1
                if self.success_count >= self.half_open_max_calls:
                    self.state = CircuitState.CLOSED
                    self.failure_count = 0
                    self.success_count = 0
                    logger.info(f"[{self.name}] Circuit breaker closed")
            else:
                self.failure_count = 0

    def record_failure(self):
        """记录失败"""
        with self._lock:
            self.failure_count += 1
            self.last_failure_time = datetime.now()

            if self.state == CircuitState.HALF_OPEN:
                self.state = CircuitState.OPEN
                logger.warning(f"[{self.name}] Circuit breaker re-opened after half-open failure")
            elif self.failure_count >= self.failure_threshold:
                self.state = CircuitState.OPEN
                logger.warning(f"[{self.name}] Circuit breaker opened after {self.failure_count} failures")


class CircuitBreakerRegistry:
    """熔断器注册表"""

    _breakers: Dict[str, CircuitBreaker] = {}
    _lock = threading.Lock()

    @classmethod
    def get_breaker(cls, name: str, **kwargs) -> CircuitBreaker:
        """获取或创建熔断器"""
        with cls._lock:
            if name not in cls._breakers:
                cls._breakers[name] = CircuitBreaker(name=name, **kwargs)
            return cls._breakers[name]

    @classmethod
    def reset(cls, name: str):
        """重置熔断器"""
        with cls._lock:
            if name in cls._breakers:
                breaker = cls._breakers[name]
                breaker.state = CircuitState.CLOSED
                breaker.failure_count = 0
                breaker.success_count = 0


def circuit_breaker(name: str, **kwargs):
    """
    熔断器装饰器

    Args:
        name: 熔断器名称
        **kwargs: CircuitBreaker 配置参数
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs_inner):
            breaker = CircuitBreakerRegistry.get_breaker(name, **kwargs)

            if not breaker.can_execute():
                raise TransientError(
                    f"Circuit breaker '{name}' is open",
                    details={"state": breaker.state.value}
                )

            try:
                result = func(*args, **kwargs_inner)
                breaker.record_success()
                return result
            except Exception as e:
                breaker.record_failure()
                raise

        return wrapper

    return decorator


# ============================================================================
# Failover Manager
# ============================================================================


@dataclass
class ProviderHealth:
    """Provider 健康状态"""
    name: str
    is_healthy: bool = True
    consecutive_failures: int = 0
    last_failure_time: Optional[datetime] = None
    last_success_time: Optional[datetime] = None
    total_requests: int = 0
    total_failures: int = 0

    @property
    def failure_rate(self) -> float:
        """计算失败率"""
        if self.total_requests == 0:
            return 0.0
        return self.total_failures / self.total_requests

    def record_success(self):
        """记录成功"""
        self.total_requests += 1
        self.consecutive_failures = 0
        self.last_success_time = datetime.now()
        self.is_healthy = True

    def record_failure(self):
        """记录失败"""
        self.total_requests += 1
        self.total_failures += 1
        self.consecutive_failures += 1
        self.last_failure_time = datetime.now()

        # 连续失败 3 次标记为不健康
        if self.consecutive_failures >= 3:
            self.is_healthy = False

    def check_recovery(self, recovery_timeout: float = 300.0) -> bool:
        """检查是否可以尝试恢复"""
        if self.is_healthy:
            return True

        if self.last_failure_time:
            elapsed = (datetime.now() - self.last_failure_time).total_seconds()
            if elapsed >= recovery_timeout:
                return True

        return False


class FailoverManager:
    """
    故障转移管理器

    自动在多个 Provider 之间切换，确保服务可用性。
    """

    def __init__(self):
        self._health: Dict[str, ProviderHealth] = {}
        self._lock = threading.Lock()

    def get_health(self, provider: str) -> ProviderHealth:
        """获取 Provider 健康状态"""
        with self._lock:
            if provider not in self._health:
                self._health[provider] = ProviderHealth(name=provider)
            return self._health[provider]

    def record_success(self, provider: str):
        """记录成功"""
        health = self.get_health(provider)
        health.record_success()

    def record_failure(self, provider: str):
        """记录失败"""
        health = self.get_health(provider)
        health.record_failure()

    def select_provider(
        self,
        primary: str,
        backups: List[str],
        recovery_timeout: float = 300.0
    ) -> str:
        """
        选择可用的 Provider

        Args:
            primary: 主 Provider
            backups: 备用 Provider 列表
            recovery_timeout: 恢复超时时间

        Returns:
            str: 选中的 Provider 名称
        """
        # 优先使用主 Provider
        primary_health = self.get_health(primary)
        if primary_health.is_healthy or primary_health.check_recovery(recovery_timeout):
            return primary

        # 尝试备用 Provider
        for backup in backups:
            backup_health = self.get_health(backup)
            if backup_health.is_healthy or backup_health.check_recovery(recovery_timeout):
                logger.info(f"Failover: {primary} -> {backup}")
                return backup

        # 所有 Provider 都不可用，返回主 Provider（让它重试）
        logger.warning(f"All providers unhealthy, falling back to {primary}")
        return primary

    def get_status(self) -> Dict[str, Dict[str, Any]]:
        """获取所有 Provider 的状态"""
        with self._lock:
            return {
                name: {
                    "is_healthy": health.is_healthy,
                    "consecutive_failures": health.consecutive_failures,
                    "failure_rate": health.failure_rate,
                    "total_requests": health.total_requests,
                    "last_failure": health.last_failure_time.isoformat() if health.last_failure_time else None,
                    "last_success": health.last_success_time.isoformat() if health.last_success_time else None,
                }
                for name, health in self._health.items()
            }


# 全局实例
failover_manager = FailoverManager()


def with_failover(
    primary_provider: str,
    backup_providers: List[str],
    get_client_func: Callable[[str], Any],
    max_retries: int = 2
):
    """
    带故障转移的装饰器

    Args:
        primary_provider: 主 Provider 名称
        backup_providers: 备用 Provider 列表
        get_client_func: 获取客户端的函数
        max_retries: 每个 Provider 的最大重试次数
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            providers = [primary_provider] + backup_providers
            last_exception = None

            for provider in providers:
                # 检查 Provider 是否可用
                health = failover_manager.get_health(provider)
                if not health.is_healthy and not health.check_recovery():
                    continue

                # 获取客户端
                try:
                    client = get_client_func(provider)
                except Exception as e:
                    logger.warning(f"Failed to get client for {provider}: {e}")
                    continue

                # 尝试调用
                for attempt in range(max_retries):
                    try:
                        result = func(client, *args, **kwargs)
                        failover_manager.record_success(provider)
                        return result
                    except (TransientError, ExternalAPIError) as e:
                        last_exception = e
                        if isinstance(e, ExternalAPIError) and not e.is_retryable:
                            failover_manager.record_failure(provider)
                            break
                        logger.warning(f"[{provider}] Attempt {attempt + 1}/{max_retries} failed: {e}")
                    except Exception as e:
                        last_exception = e
                        failover_manager.record_failure(provider)
                        break

                failover_manager.record_failure(provider)

            # 所有 Provider 都失败
            if last_exception:
                raise last_exception
            raise TransientError("All providers failed")

        return wrapper

    return decorator


# ============================================================================
# Quota Manager
# ============================================================================


@dataclass
class QuotaInfo:
    """配额信息"""
    provider: str
    limit: int  # 配额上限
    used: int = 0  # 已使用
    reset_time: Optional[datetime] = None  # 重置时间

    @property
    def remaining(self) -> int:
        """剩余配额"""
        return max(0, self.limit - self.used)

    @property
    def is_exhausted(self) -> bool:
        """配额是否耗尽"""
        return self.used >= self.limit

    def consume(self, amount: int = 1) -> bool:
        """消耗配额"""
        if self.used + amount > self.limit:
            return False
        self.used += amount
        return True

    def reset(self):
        """重置配额"""
        self.used = 0
        self.reset_time = datetime.now() + timedelta(days=1)


class QuotaManager:
    """配额管理器"""

    def __init__(self):
        self._quotas: Dict[str, QuotaInfo] = {}
        self._lock = threading.Lock()

    def set_quota(self, provider: str, limit: int):
        """设置配额"""
        with self._lock:
            self._quotas[provider] = QuotaInfo(provider=provider, limit=limit)

    def get_quota(self, provider: str) -> Optional[QuotaInfo]:
        """获取配额信息"""
        with self._lock:
            return self._quotas.get(provider)

    def consume(self, provider: str, amount: int = 1) -> bool:
        """消耗配额"""
        with self._lock:
            quota = self._quotas.get(provider)
            if quota is None:
                return True  # 未设置配额，允许通过
            return quota.consume(amount)

    def check_and_reset(self, provider: str):
        """检查并重置过期配额"""
        with self._lock:
            quota = self._quotas.get(provider)
            if quota and quota.reset_time and datetime.now() >= quota.reset_time:
                quota.reset()


# 全局实例
quota_manager = QuotaManager()
