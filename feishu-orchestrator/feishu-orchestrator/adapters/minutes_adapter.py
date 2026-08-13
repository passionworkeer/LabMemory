"""
妙记适配器 - MinutesAdapter
负责从飞书妙记获取逐字稿、说话人、时间戳、章节等内容
"""
import json
import re
import subprocess
from dataclasses import dataclass, field
from typing import Optional, List
from pathlib import Path

from core.config import Config
from core.utils import now_iso, generate_id, safe_get
from reliability.integration_log import integration_log
from reliability.retry_engine import with_retry


# 逐字稿行格式：可选时间戳前缀 + 说话人 + 分隔符 + 正文
# 例：[00:01:23] 张三：我们把温度调到 70℃
_TRANSCRIPT_LINE_RE = re.compile(
    r"^\s*(?:\[(?P<ts>[\d:：.]+)\]\s*)?(?P<speaker>[^:：\[\]]{1,32})[:：]\s*(?P<text>.+)$"
)



@dataclass
class TranscriptItem:
    """逐字稿条目"""
    speaker: str
    start_offset_sec: int
    end_offset_sec: int
    text: str


@dataclass
class Chapter:
    """章节"""
    title: str
    start_offset_sec: int


@dataclass
class MinutesDetail:
    """妙记详情"""
    minute_token: str
    title: str
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    organizer: Optional[str] = None
    participants: List[str] = field(default_factory=list)
    transcript: List[TranscriptItem] = field(default_factory=list)
    chapters: List[Chapter] = field(default_factory=list)
    summary: Optional[str] = None
    action_items: List[str] = field(default_factory=list)
    source_url: Optional[str] = None


class MinutesAdapter:
    """妙记适配器"""

    def __init__(self):
        self.mock_data_dir = Path(__file__).parent.parent / "mock"

    @with_retry(interface_name="minutes.search")
    def search(self, query: str, start_time: str = "", end_time: str = "") -> list:
        """
        搜索妙记
        :param query: 搜索关键词
        :param start_time: 开始时间
        :param end_time: 结束时间
        :return: 妙记列表
        """
        if Config.is_mock_mode():
            return self._mock_search(query)

        return self._real_search(query, start_time, end_time)

    @with_retry(interface_name="minutes.get_detail")
    def get_detail(self, minute_token: str) -> MinutesDetail:
        """
        获取妙记详情
        :param minute_token: 妙记 token
        :return: 妙记详情
        """
        integration_log.log(
            direction="outbound",
            interface="minutes.get_detail",
            input_data={"minute_token": minute_token},
            status="start"
        )

        try:
            if Config.is_mock_mode():
                detail = self._mock_get_detail(minute_token)
            else:
                detail = self._real_get_detail(minute_token)

            integration_log.log(
                direction="outbound",
                interface="minutes.get_detail",
                input_data={"minute_token": minute_token},
                output_data={"title": detail.title, "transcript_count": len(detail.transcript)},
                status="success"
            )
            return detail

        except Exception as e:
            integration_log.log(
                direction="outbound",
                interface="minutes.get_detail",
                input_data={"minute_token": minute_token},
                error=str(e),
                status="failed"
            )
            raise

    def get_by_meeting_id(self, meeting_id: str) -> Optional[MinutesDetail]:
        """
        通过 meeting_id 反查妙记
        :param meeting_id: 会议 ID
        :return: 妙记详情
        """
        if Config.is_mock_mode():
            return self._mock_get_by_meeting_id(meeting_id)

        # 真实模式：先搜索再匹配
        results = self.search(query=meeting_id)
        for item in results:
            if item.get("meeting_id") == meeting_id:
                return self.get_detail(item["minute_token"])
        return None

    def get_by_url(self, url: str) -> MinutesDetail:
        """
        通过妙记链接获取详情
        :param url: 妙记链接
        :return: 妙记详情
        """
        # 从 URL 中提取 minute_token
        minute_token = self._extract_token_from_url(url)
        if not minute_token:
            raise ValueError(f"无法从链接中提取 minute_token: {url}")

        detail = self.get_detail(minute_token)
        detail.source_url = url
        return detail

    def _extract_token_from_url(self, url: str) -> Optional[str]:
        """从妙记链接中提取 token"""
        patterns = [
            r"/minutes/([a-zA-Z0-9]+)",
            r"minute_token=([a-zA-Z0-9]+)",
        ]
        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                return match.group(1)
        return None

    # ==================== Mock 实现 ====================

    def _mock_search(self, query: str) -> list:
        """Mock 搜索"""
        mock_file = self.mock_data_dir / "sample_minutes.json"
        if not mock_file.exists():
            return []

        with open(mock_file, "r", encoding="utf-8") as f:
            data = json.load(f)

        results = []
        for item in data.get("list", []):
            if query in item.get("title", "") or query in item.get("minute_token", ""):
                results.append(item)
        return results

    def _mock_get_detail(self, minute_token: str) -> MinutesDetail:
        """Mock 获取详情"""
        mock_file = self.mock_data_dir / "sample_minutes_detail.json"
        if not mock_file.exists():
            # 返回一个默认的 mock 数据
            return self._generate_sample_detail(minute_token)

        with open(mock_file, "r", encoding="utf-8") as f:
            data = json.load(f)

        return self._parse_detail_from_json(data)

    def _mock_get_by_meeting_id(self, meeting_id: str) -> Optional[MinutesDetail]:
        """Mock 通过 meeting_id 获取"""
        mock_file = self.mock_data_dir / "sample_minutes_detail.json"
        if not mock_file.exists():
            return None

        with open(mock_file, "r", encoding="utf-8") as f:
            data = json.load(f)

        if data.get("meeting_id") == meeting_id:
            return self._parse_detail_from_json(data)
        return None

    def _generate_sample_detail(self, minute_token: str) -> MinutesDetail:
        """生成示例妙记数据"""
        return MinutesDetail(
            minute_token=minute_token,
            title="实验方案评审会 - 示例",
            start_time="2026-08-05T10:00:00+08:00",
            end_time="2026-08-05T11:30:00+08:00",
            organizer="张三",
            participants=["张三", "李四", "王五", "赵六"],
            transcript=[
                TranscriptItem(
                    speaker="张三",
                    start_offset_sec=0,
                    end_offset_sec=45,
                    text="大家好，今天我们来评审一下新的实验方案。首先我介绍一下背景，我们之前的实验 EXP-2026-001 结果不太理想，需要调整参数。"
                ),
                TranscriptItem(
                    speaker="李四",
                    start_offset_sec=45,
                    end_offset_sec=120,
                    text="我来说一下方案A。我们建议把温度从20度调整到25度，同时把反应时间从30分钟延长到45分钟。根据我们的模拟，这样转化率应该能提升15%左右。"
                ),
                TranscriptItem(
                    speaker="王五",
                    start_offset_sec=120,
                    end_offset_sec=200,
                    text="方案A听起来不错，但我有个顾虑。温度升高到25度会不会导致副反应增加？我们之前在28度的时候发现过杂质超标的问题。"
                ),
                TranscriptItem(
                    speaker="李四",
                    start_offset_sec=200,
                    end_offset_sec=280,
                    text="这个问题我们考虑过了。根据文献，25度是一个比较安全的阈值，副反应增加的幅度很小。而且我们可以在实验中增加中间检测点，一旦发现异常就及时终止。"
                ),
                TranscriptItem(
                    speaker="赵六",
                    start_offset_sec=280,
                    end_offset_sec=350,
                    text="我补充一下成本的问题。方案A的原料成本会增加8%左右，但是如果转化率真的能提升15%，总体算下来单位成本还是下降的。"
                ),
                TranscriptItem(
                    speaker="张三",
                    start_offset_sec=350,
                    end_offset_sec=420,
                    text="好的，那大家觉得方案A可行吗？我觉得可以先做一批小试验证一下。李四，你那边能安排一下吗？"
                ),
                TranscriptItem(
                    speaker="李四",
                    start_offset_sec=420,
                    end_offset_sec=460,
                    text="没问题，我这周就能安排下去，预计下周三能出结果。"
                ),
                TranscriptItem(
                    speaker="张三",
                    start_offset_sec=460,
                    end_offset_sec=500,
                    text="好，那就这么定了。我们采用方案A，先做小试验证。王五你负责中间检测点的监控，赵六你跟进成本核算。"
                ),
                TranscriptItem(
                    speaker="王五",
                    start_offset_sec=500,
                    end_offset_sec=530,
                    text="好的，我会安排好检测计划。"
                ),
                TranscriptItem(
                    speaker="赵六",
                    start_offset_sec=530,
                    end_offset_sec=560,
                    text="收到，成本那边我来跟进。"
                ),
            ],
            chapters=[
                Chapter(title="背景介绍", start_offset_sec=0),
                Chapter(title="方案A讨论", start_offset_sec=45),
                Chapter(title="风险与成本评估", start_offset_sec=120),
                Chapter(title="决策与行动项", start_offset_sec=350),
            ],
            summary="本次会议评审了实验 EXP-2026-001 的调整方案。经过讨论，团队决定采用方案A：将温度从20度调整到25度，反应时间从30分钟延长到45分钟。预计转化率提升15%，单位成本下降。本周安排小试，下周三出结果。",
            action_items=[
                "李四：安排方案A的小试实验，下周三出结果",
                "王五：负责实验中间检测点的监控",
                "赵六：跟进方案A的成本核算",
            ],
            source_url=f"https://bytedance.larkoffice.com/minutes/{minute_token}"
        )

    # ==================== 真实实现 ====================

    def _real_search(self, query: str, start_time: str, end_time: str) -> list:
        """真实搜索妙记（lark-cli minutes +search）"""
        try:
            cmd = [
                Config.get_lark_cli_command(), "minutes", "+search",
                "--query", query,
                "--as", "user",
            ]
            if start_time:
                cmd.extend(["--start", start_time])
            if end_time:
                cmd.extend(["--end", end_time])

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=30
            )

            if result.returncode != 0:
                raise Exception(f"lark-cli 执行失败: {result.stderr or result.stdout}")

            data = json.loads(result.stdout)
            return safe_get(data, "data", "minutes", default=None) or data.get("items", [])

        except FileNotFoundError:
            raise Exception("lark-cli 未安装，请先安装飞书 CLI：npm install -g @larksuite/cli")
        except subprocess.TimeoutExpired:
            raise Exception("搜索妙记超时")
        except json.JSONDecodeError:
            raise Exception("解析妙记搜索结果失败")

    def _real_get_detail(self, minute_token: str) -> MinutesDetail:
        """
        真实获取妙记详情（lark-cli minutes +detail）

        注意：`--transcript` 不在 stdout 返回逐字稿正文，而是把文件落盘，
        stdout 只给出 `artifacts.transcript_file` 路径，需要二次读取该文件。
        """
        try:
            output_dir = Config.DATA_DIR / "minutes" / minute_token
            output_dir.mkdir(parents=True, exist_ok=True)
            cli_output_dir = output_dir  # 基于 Config.DATA_DIR，与落盘/读取目录一致，不依赖 cwd
            cmd = [
                Config.get_lark_cli_command(), "minutes", "+detail",
                "--minute-tokens", minute_token,
                "--summary", "--todo", "--chapter", "--transcript",
                "--overwrite", "--output-dir", str(cli_output_dir),
                "--as", "user",
            ]

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=120,
                cwd=str(Config.PROJECT_ROOT),
            )

            if result.returncode != 0:
                raise Exception(f"lark-cli 执行失败: {result.stderr or result.stdout}")

            payload = json.loads(result.stdout)

        except FileNotFoundError:
            raise Exception("lark-cli 未安装，请先安装飞书 CLI：npm install -g @larksuite/cli")
        except subprocess.TimeoutExpired:
            raise Exception("获取妙记详情超时")
        except json.JSONDecodeError:
            raise Exception("解析妙记详情失败")

        minutes = safe_get(payload, "data", "minutes", default=None) or payload.get("minutes", [])
        if not minutes:
            raise Exception(f"妙记 {minute_token} 未返回详情")

        return self._parse_detail_from_cli(minutes[0], minute_token)

    def _parse_detail_from_cli(self, minute: dict, minute_token: str) -> MinutesDetail:
        """
        解析 `minutes +detail` 的单条输出。

        该命令只返回 minute_token / title / note_id / artifacts，
        不含参会人、起止时间、组织者，这些字段留空由上层显式处理，不得伪造。
        """
        artifacts = minute.get("artifacts", {}) or {}

        transcript_file = artifacts.get("transcript_file", "")
        transcript = self._read_transcript_file(transcript_file) if transcript_file else []
        if not transcript:
            raise Exception(
                f"妙记 {minute_token} 逐字稿缺失"
                f"（transcript_file={transcript_file or '未返回'}）"
            )

        chapters = []
        for item in artifacts.get("chapters", []) or []:
            chapters.append(Chapter(
                title=item.get("title", ""),
                start_offset_sec=int(item.get("start_offset_sec", 0) or 0)
            ))

        action_items = [
            item.get("content", "")
            for item in (artifacts.get("todos", []) or [])
            if item.get("content")
        ]

        return MinutesDetail(
            minute_token=minute.get("minute_token", minute_token),
            title=minute.get("title", "未命名会议"),
            start_time=None,
            end_time=None,
            organizer=None,
            participants=[],
            transcript=transcript,
            chapters=chapters,
            summary=artifacts.get("summary"),
            action_items=action_items,
            source_url=minute.get("url", ""),
        )

    def _read_transcript_file(self, transcript_file: str) -> List[TranscriptItem]:
        """
        读取落盘的逐字稿文件（默认 ./minutes/{minute_token}/transcript.txt）。

        行格式尚未在真实妙记上验证，因此按「可选时间戳 + 说话人 + 正文」宽松解析，
        无法匹配的行退化为整行正文、说话人未知，MUST NOT 丢弃内容。
        """
        # transcript_file 由 lark-cli 基于 --output-dir（Config.DATA_DIR 基绝对路径）返回；
        # is_absolute 时直接采用，相对路径仅作回退拼到 DATA_DIR/minutes 下，MUST NOT 与返回路径前缀重复。
        path = Path(transcript_file)
        if not path.is_absolute():
            path = Config.DATA_DIR / "minutes" / path
        try:
            path.resolve().relative_to((Config.DATA_DIR / "minutes").resolve())
        except ValueError:
            return []
        if not path.exists() or not path.is_file():
            return []

        items: List[TranscriptItem] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue

            match = _TRANSCRIPT_LINE_RE.match(line)
            if match:
                offset = self._parse_timestamp(match.group("ts"))
                items.append(TranscriptItem(
                    speaker=match.group("speaker").strip(),
                    start_offset_sec=offset,
                    end_offset_sec=offset,
                    text=match.group("text").strip(),
                ))
            else:
                items.append(TranscriptItem(
                    speaker="未知",
                    start_offset_sec=0,
                    end_offset_sec=0,
                    text=line,
                ))

        return items

    @staticmethod
    def _parse_timestamp(ts: Optional[str]) -> int:
        """把 HH:MM:SS / MM:SS 形式的时间戳转为秒；无法解析时返回 0"""
        if not ts:
            return 0

        parts = ts.replace("：", ":").split(":")
        seconds = 0
        try:
            for part in parts:
                seconds = seconds * 60 + int(float(part))
        except ValueError:
            return 0
        return seconds


    def to_meeting_package(self, detail: MinutesDetail, source: str = "feishu_minutes") -> dict:
        """转换为 MeetingPackage 格式"""
        return {
            "schema_version": "1.0.0",
            "source": source,
            "source_object_id": detail.minute_token,
            "meeting_id": "",  # 需要额外获取
            "title": detail.title,
            "start_time": detail.start_time,
            "end_time": detail.end_time,
            "organizer": detail.organizer,
            "participants": detail.participants,
            "content": {
                "transcript": [
                    {
                        "speaker": t.speaker,
                        "start_offset_sec": t.start_offset_sec,
                        "end_offset_sec": t.end_offset_sec,
                        "text": t.text
                    }
                    for t in detail.transcript
                ],
                "chapters": [
                    {
                        "title": c.title,
                        "start_offset_sec": c.start_offset_sec
                    }
                    for c in detail.chapters
                ],
                "summary": detail.summary,
                "action_items": detail.action_items
            },
            "source_url": detail.source_url or "",
            "captured_at": now_iso(),
            "metadata": {}
        }


# 单例
minutes_adapter = MinutesAdapter()
