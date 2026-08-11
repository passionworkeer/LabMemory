"""
幂等控制 - Idempotency Guard
防止重复事件导致重复处理
"""
import json
from pathlib import Path
from typing import Optional

from core.config import Config
from core.utils import now_iso


class IdempotencyGuard:
    """幂等守卫"""

    def __init__(self):
        self.store_dir = Config.DATA_DIR / "idempotency"
        self.store_dir.mkdir(exist_ok=True)

    def _get_key_path(self, key: str) -> Path:
        """获取 key 对应的文件路径"""
        # 使用 hash 避免特殊字符
        import hashlib
        safe_key = hashlib.md5(key.encode()).hexdigest()
        return self.store_dir / f"{safe_key}.json"

    def check(self, idempotency_key: str) -> Optional[dict]:
        """
        检查是否已处理
        :return: 如果已处理，返回之前的结果；否则返回 None
        """
        key_path = self._get_key_path(idempotency_key)
        if not key_path.exists():
            return None

        try:
            with open(key_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data.get("result")
        except Exception:
            return None

    def mark(self, idempotency_key: str, result: dict, ttl_seconds: int = 86400 * 7):
        """
        标记为已处理
        :param idempotency_key: 幂等键
        :param result: 处理结果
        :param ttl_seconds: 过期时间（秒），默认7天
        """
        key_path = self._get_key_path(idempotency_key)

        data = {
            "key": idempotency_key,
            "result": result,
            "created_at": now_iso(),
            "ttl_seconds": ttl_seconds,
        }

        try:
            with open(key_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"[IdempotencyGuard] 写入失败: {e}")

    def acquire(self, idempotency_key: str) -> bool:
        """原子抢占处理权（O_CREAT|O_EXCL）。成功=True（创建占位文件，获得执行权）；False=已被占/已处理。

        消除 check→业务→mark 三步 TOCTOU：调用方在执行业务副作用前 acquire，
        失败说明另一并发/重试已占，直接返回缓存或「处理中」。
        """
        import os
        key_path = self._get_key_path(idempotency_key)
        try:
            fd = os.open(str(key_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.close(fd)
            return True
        except (FileExistsError, OSError):
            return False

    def is_processed(self, idempotency_key: str) -> bool:
        """简单判断是否已处理（占位文件存在即视为已处理/处理中）。"""
        return self._get_key_path(idempotency_key).exists()

    def cleanup_expired(self):
        """清理过期的幂等记录"""
        import time
        now = time.time()
        count = 0

        for file_path in self.store_dir.glob("*.json"):
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    data = json.load(f)

                created_at = data.get("created_at", "")
                ttl = data.get("ttl_seconds", 86400 * 7)

                # 简单的过期判断
                from datetime import datetime
                try:
                    created_time = datetime.fromisoformat(created_at)
                    age = (datetime.now() - created_time).total_seconds()
                    if age > ttl:
                        file_path.unlink()
                        count += 1
                except Exception:
                    continue
            except Exception:
                continue

        return count


# 单例
idempotency_guard = IdempotencyGuard()
