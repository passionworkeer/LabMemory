"""
状态机 - State Machine
管理会议/妙记的处理状态流转
"""
import json
from enum import Enum
from pathlib import Path
from typing import Optional, Dict, Any

from core.config import Config
from core.utils import now_iso, generate_id


class MeetingState(Enum):
    """会议处理状态"""
    WAITING_MINUTES = "waiting_minutes"  # 会议已结束，等妙记
    MINUTES_READY = "minutes_ready"      # 妙记已就绪
    COMPILING = "compiling"              # Aily 编译中
    SUBMITTED = "submitted"              # 已提交平台
    REVIEWING = "reviewing"              # 复核中
    APPROVED = "approved"                # 已批准
    COMPLETED = "completed"              # 全链路完成
    BLOCKED = "blocked"                  # 已阻断
    FAILED = "failed"                    # 失败


class StateMachine:
    """状态机"""

    def __init__(self):
        self.state_dir = Config.DATA_DIR / "state"
        self.state_dir.mkdir(exist_ok=True)

    def _get_state_path(self, object_id: str) -> Path:
        """获取状态文件路径"""
        import hashlib
        safe_id = hashlib.md5(object_id.encode()).hexdigest()
        return self.state_dir / f"{safe_id}.json"

    def get_state(self, object_id: str) -> Optional[dict]:
        """获取对象状态"""
        path = self._get_state_path(object_id)
        if not path.exists():
            return None

        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return None

    def set_state(self, object_id: str, state: MeetingState, extra: Optional[dict] = None):
        """设置对象状态"""
        path = self._get_state_path(object_id)

        current = self.get_state(object_id) or {}
        old_state = current.get("state")

        current.update({
            "object_id": object_id,
            "state": state.value,
            "updated_at": now_iso(),
        })

        if extra:
            current.update(extra)

        if "created_at" not in current:
            current["created_at"] = now_iso()

        # 记录状态流转历史
        history = current.get("history", [])
        history.append({
            "from": old_state,
            "to": state.value,
            "timestamp": now_iso(),
        })
        current["history"] = history

        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(current, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"[StateMachine] 写入状态失败: {e}")

    def transition(
        self,
        object_id: str,
        from_state: Optional[MeetingState],
        to_state: MeetingState,
        extra: Optional[dict] = None,
    ) -> bool:
        """
        状态流转（带前置状态校验）
        :param object_id: 对象 ID
        :param from_state: 期望的当前状态（None 表示不校验）
        :param to_state: 目标状态
        :param extra: 额外数据
        :return: 是否成功流转
        """
        current = self.get_state(object_id)

        # 校验前置状态
        if from_state is not None:
            if not current:
                return False
            if current.get("state") != from_state.value:
                return False

        # 执行流转
        self.set_state(object_id, to_state, extra)
        return True

    def is_in_state(self, object_id: str, state: MeetingState) -> bool:
        """检查是否处于指定状态"""
        current = self.get_state(object_id)
        if not current:
            return False
        return current.get("state") == state.value

    def get_all_states(self, limit: int = 100) -> list:
        """获取所有状态记录"""
        states = []
        for file_path in sorted(self.state_dir.glob("*.json"), reverse=True):
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    states.append(json.load(f))
                if len(states) >= limit:
                    break
            except Exception:
                continue
        return states

    def get_by_state(self, state: MeetingState, limit: int = 50) -> list:
        """按状态查询"""
        result = []
        for s in self.get_all_states(limit=200):
            if s.get("state") == state.value:
                result.append(s)
                if len(result) >= limit:
                    break
        return result

    def cleanup_old(self, days: int = 30):
        """清理旧的状态记录"""
        from datetime import datetime, timedelta
        cutoff = datetime.now() - timedelta(days=days)
        count = 0

        for file_path in self.state_dir.glob("*.json"):
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    data = json.load(f)

                created_at = data.get("created_at", "")
                if not created_at:
                    continue

                try:
                    created_time = datetime.fromisoformat(created_at)
                    if created_time < cutoff:
                        file_path.unlink()
                        count += 1
                except Exception:
                    continue
            except Exception:
                continue

        return count


# 单例
state_machine = StateMachine()
