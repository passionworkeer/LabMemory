"""
重试引擎 - Retry Engine
处理网络超时、限流等可重试错误
"""
import time
import random
from typing import Callable, Any, Optional, List, Type
from functools import wraps

from core.config import Config
from reliability.integration_log import integration_log


class RetryableError(Exception):
    """可重试的错误"""
    pass


class NonRetryableError(Exception):
    """不可重试的错误"""
    pass


class RetryEngine:
    """重试引擎"""

    def __init__(
        self,
        max_retries: Optional[int] = None,
        base_delay: Optional[int] = None,
        max_delay: int = 60,
        backoff_factor: float = 2.0,
        jitter: bool = True,
        retryable_exceptions: Optional[List[Type[Exception]]] = None,
    ):
        self.max_retries = max_retries or Config.MAX_RETRIES
        self.base_delay = base_delay or Config.RETRY_BASE_DELAY
        self.max_delay = max_delay
        self.backoff_factor = backoff_factor
        self.jitter = jitter
        self.retryable_exceptions = retryable_exceptions or [
            RetryableError,
            TimeoutError,
            ConnectionError,
        ]

    def is_retryable(self, exception: Exception) -> bool:
        """判断异常是否可重试"""
        # 明确标记为不可重试的
        if isinstance(exception, NonRetryableError):
            return False

        # 在可重试列表中的
        for exc_type in self.retryable_exceptions:
            if isinstance(exception, exc_type):
                return True

        # 飞书限流错误（9999999）
        if "9999999" in str(exception) or "rate limit" in str(exception).lower():
            return True

        # 网络相关错误
        error_msg = str(exception).lower()
        if any(keyword in error_msg for keyword in ["timeout", "timed out", "connection", "502", "503", "504"]):
            return True

        return False

    def calculate_delay(self, attempt: int) -> float:
        """计算第 N 次重试的延迟时间"""
        delay = self.base_delay * (self.backoff_factor ** attempt)
        delay = min(delay, self.max_delay)

        if self.jitter:
            # 添加随机抖动，避免惊群效应
            delay = delay * (0.5 + random.random() * 0.5)

        return delay

    def execute(
        self,
        func: Callable,
        *args,
        interface_name: str = "",
        **kwargs,
    ) -> Any:
        """
        执行函数，带重试
        :param func: 要执行的函数
        :param interface_name: 接口名（用于日志）
        :return: 函数返回值
        """
        last_exception = None

        for attempt in range(self.max_retries + 1):
            try:
                result = func(*args, **kwargs)

                # 成功后，如果是重试的，记录一下
                if attempt > 0:
                    integration_log.log(
                        direction="outbound",
                        interface=interface_name or func.__name__,
                        input_data={"attempt": attempt + 1},
                        output_data={"result": "success_after_retry"},
                        status="success",
                    )

                return result

            except Exception as e:
                last_exception = e

                # 判断是否可重试
                if not self.is_retryable(e):
                    raise

                # 已经是最后一次重试了
                if attempt >= self.max_retries:
                    break

                # 计算延迟
                delay = self.calculate_delay(attempt)

                # 记录重试日志
                integration_log.log(
                    direction="outbound",
                    interface=interface_name or func.__name__,
                    input_data={"attempt": attempt + 1, "delay_seconds": round(delay, 2)},
                    error=str(e),
                    status="retrying",
                )

                # 等待
                time.sleep(delay)

        # 所有重试都失败了
        raise last_exception

    def retry_decorator(self, interface_name: str = ""):
        """重试装饰器"""
        def decorator(func):
            @wraps(func)
            def wrapper(*args, **kwargs):
                return self.execute(
                    func,
                    *args,
                    interface_name=interface_name or func.__name__,
                    **kwargs,
                )
            return wrapper
        return decorator


# 全局默认重试引擎
default_retry_engine = RetryEngine()


def with_retry(func=None, *, interface_name: str = ""):
    """
    便捷重试装饰器
    用法：
        @with_retry
        def my_func():
            pass

        @with_retry(interface_name="my_api")
        def my_func():
            pass
    """
    if func is not None:
        # 直接装饰
        return default_retry_engine.retry_decorator()(func)
    else:
        # 带参数装饰
        return default_retry_engine.retry_decorator(interface_name)
