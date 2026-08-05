"""
集成日志 - Integration Log
记录所有外部系统调用，用于排查问题和演示异常案例
"""
import json
import time
from pathlib import Path
from datetime import datetime
from typing import Optional

from core.config import Config
from core.utils import generate_id


class IntegrationLog:
    """集成日志"""

    def __init__(self):
        self.log_dir = Config.DATA_DIR / "integration_logs"
        self.log_dir.mkdir(exist_ok=True)

    def log(
        self,
        direction: str,  # inbound / outbound
        interface: str,
        input_data: dict,
        output_data: Optional[dict] = None,
        error: Optional[str] = None,
        status: str = "success",  # start / success / failed / retrying
        duration_ms: Optional[int] = None,
        request_id: Optional[str] = None,
    ) -> str:
        """
        记录一条集成日志
        :return: log_id
        """
        log_id = generate_id("intlog")
        now = datetime.now().isoformat()

        log_entry = {
            "log_id": log_id,
            "timestamp": now,
            "direction": direction,
            "interface": interface,
            "status": status,
            "input_data": self._sanitize(input_data),
            "output_data": self._sanitize(output_data) if output_data else None,
            "error": error,
            "duration_ms": duration_ms,
            "request_id": request_id,
        }

        # 按天分文件
        date_str = datetime.now().strftime("%Y%m%d")
        log_file = self.log_dir / f"integration_{date_str}.jsonl"

        try:
            with open(log_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")
        except Exception as e:
            print(f"[IntegrationLog] 写入日志失败: {e}")

        return log_id

    def _sanitize(self, data: dict) -> dict:
        """脱敏处理：移除敏感字段"""
        if not isinstance(data, dict):
            return data

        sensitive_keys = ["token", "secret", "password", "api_key", "access_token"]
        result = {}
        for k, v in data.items():
            if any(s in k.lower() for s in sensitive_keys):
                result[k] = "***"
            elif isinstance(v, dict):
                result[k] = self._sanitize(v)
            else:
                result[k] = v
        return result

    def get_logs(
        self,
        interface: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 100,
    ) -> list:
        """查询集成日志"""
        logs = []
        # 读取最近3天的日志
        for i in range(3):
            from datetime import timedelta
            date_str = (datetime.now() - timedelta(days=i)).strftime("%Y%m%d")
            log_file = self.log_dir / f"integration_{date_str}.jsonl"
            if not log_file.exists():
                continue

            with open(log_file, "r", encoding="utf-8") as f:
                for line in f:
                    try:
                        entry = json.loads(line.strip())
                        if interface and entry.get("interface") != interface:
                            continue
                        if status and entry.get("status") != status:
                            continue
                        logs.append(entry)
                        if len(logs) >= limit:
                            return logs
                    except json.JSONDecodeError:
                        continue

        return logs

    def get_failed_logs(self, limit: int = 50) -> list:
        """获取失败的日志"""
        return self.get_logs(status="failed", limit=limit)

    def replay(self, log_id: str) -> dict:
        """重放一条日志（重新执行）"""
        # 查找日志
        log_entry = None
        for i in range(7):
            from datetime import timedelta
            date_str = (datetime.now() - timedelta(days=i)).strftime("%Y%m%d")
            log_file = self.log_dir / f"integration_{date_str}.jsonl"
            if not log_file.exists():
                continue

            with open(log_file, "r", encoding="utf-8") as f:
                for line in f:
                    try:
                        entry = json.loads(line.strip())
                        if entry.get("log_id") == log_id:
                            log_entry = entry
                            break
                    except json.JSONDecodeError:
                        continue
            if log_entry:
                break

        if not log_entry:
            raise ValueError(f"未找到日志: {log_id}")

        # 这里只是返回日志信息，实际重放逻辑由调用方实现
        return log_entry


# 单例
integration_log = IntegrationLog()
