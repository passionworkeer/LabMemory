"""
工具函数
"""
import hashlib
import json
import uuid
from datetime import datetime, timezone, timedelta

# 北京时间
CST = timezone(timedelta(hours=8))


def now_iso() -> str:
    """获取当前时间 ISO 格式（北京时间）"""
    return datetime.now(CST).isoformat()


def generate_id(prefix: str = "") -> str:
    """生成唯一 ID"""
    uid = uuid.uuid4().hex[:12]
    return f"{prefix}_{uid}" if prefix else uid


def compute_hash(data: dict) -> str:
    """计算字典的 SHA256 哈希"""
    content = json.dumps(data, sort_keys=True, ensure_ascii=False)
    return "sha256:" + hashlib.sha256(content.encode()).hexdigest()


def seconds_to_hms(seconds: int) -> str:
    """秒数转 HH:MM:SS"""
    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60
    return f"{h:02d}:{m:02d}:{s:02d}"


def safe_get(d: dict, *keys, default=None):
    """安全获取嵌套字典的值"""
    current = d
    for key in keys:
        if not isinstance(current, dict):
            return default
        current = current.get(key)
        if current is None:
            return default
    return current


def truncate_text(text: str, max_len: int = 200) -> str:
    """截断文本"""
    if len(text) <= max_len:
        return text
    return text[:max_len] + "..."
