"""
Aily 决策编译适配器 - AilyAdapter
负责调用 Aily Skill 将会议自然语言编译为结构化候选决策
"""
import json
import re
import subprocess
from pathlib import Path
from typing import List, Optional

from core.config import Config
from core.utils import now_iso, generate_id, compute_hash, safe_get, seconds_to_hms
from reliability.integration_log import integration_log
from reliability.retry_engine import with_retry


class AilyAdapter:
    """Aily 决策编译适配器"""

    # 版本号
    SKILL_VERSION = "v1.0.0"
    PROMPT_VERSION = "v1.0.0"
    MODEL_VERSION = "default"

    def __init__(self):
        self.mock_data_dir = Path(__file__).parent.parent / "mock"
        self.skill_id = Config.AILY_SKILL_ID
        self.api_base = Config.AILY_API_BASE

    def compile(self, meeting_package: dict) -> dict:
        """
        编译会议内容为候选决策包
        :param meeting_package: MeetingPackage 字典
        :return: CandidatePackage 字典
        """
        input_hash = compute_hash(meeting_package)
        source_package_id = meeting_package.get("source_object_id", "")

        integration_log.log(
            direction="outbound",
            interface="aily.compile",
            input_data={
                "source_package_id": source_package_id,
                "input_hash": input_hash,
                "transcript_length": len(meeting_package.get("content", {}).get("transcript", [])),
            },
            status="start"
        )

        try:
            if Config.is_mock_mode():
                candidate_package = self._mock_compile(meeting_package)
            else:
                candidate_package = self._real_compile(meeting_package)

            # 补充元信息
            candidate_package["schema_version"] = "1.0.0"
            candidate_package["source_package_id"] = source_package_id
            candidate_package["aily_skill_version"] = self.SKILL_VERSION
            candidate_package["model_version"] = self.MODEL_VERSION
            candidate_package["prompt_version"] = self.PROMPT_VERSION
            candidate_package["input_hash"] = input_hash
            candidate_package["compiled_at"] = now_iso()

            # 规则二次校验
            candidate_package = self._rule_validate(candidate_package)

            integration_log.log(
                direction="outbound",
                interface="aily.compile",
                input_data={"source_package_id": source_package_id, "input_hash": input_hash},
                output_data={
                    "candidate_count": len(candidate_package.get("candidates", [])),
                    "risk_count": len(candidate_package.get("risks", [])),
                    "action_count": len(candidate_package.get("action_items", [])),
                },
                status="success"
            )

            return candidate_package

        except Exception as e:
            integration_log.log(
                direction="outbound",
                interface="aily.compile",
                input_data={"source_package_id": source_package_id, "input_hash": input_hash},
                error=str(e),
                status="failed"
            )
            raise

    def _segment_meeting(self, meeting_package: dict, max_segment_chars: int = 8000) -> List[dict]:
        """
        将长会议分段，避免超长输入
        :param meeting_package: 会议包
        :param max_segment_chars: 每段最大字符数
        :return: 分段列表
        """
        transcript = meeting_package.get("content", {}).get("transcript", [])
        chapters = meeting_package.get("content", {}).get("chapters", [])

        # 如果内容很短，直接返回一段
        total_chars = sum(len(t.get("text", "")) for t in transcript)
        if total_chars <= max_segment_chars:
            return [meeting_package]

        # 按章节分段
        segments = []
        current_segment = []
        current_chars = 0
        current_chapter = ""

        for item in transcript:
            # 找到当前条目所属的章节
            item_chapter = self._find_chapter(item.get("start_offset_sec", 0), chapters)

            text = item.get("text", "")
            text_len = len(text)

            # 如果加上这段会超过限制，且当前段不为空，就分段
            if current_chars + text_len > max_segment_chars and current_segment:
                segments.append({
                    "chapter": current_chapter,
                    "transcript": current_segment,
                    "start_offset": current_segment[0].get("start_offset_sec", 0),
                    "end_offset": current_segment[-1].get("end_offset_sec", 0),
                })
                current_segment = []
                current_chars = 0

            current_segment.append(item)
            current_chars += text_len
            current_chapter = item_chapter

        # 最后一段
        if current_segment:
            segments.append({
                "chapter": current_chapter,
                "transcript": current_segment,
                "start_offset": current_segment[0].get("start_offset_sec", 0),
                "end_offset": current_segment[-1].get("end_offset_sec", 0),
            })

        return segments

    def _find_chapter(self, offset_sec: int, chapters: list) -> str:
        """找到某个时间点所属的章节"""
        current_chapter = ""
        for ch in chapters:
            if ch.get("start_offset_sec", 0) <= offset_sec:
                current_chapter = ch.get("title", "")
            else:
                break
        return current_chapter

    def _merge_and_dedup(self, segment_results: List[dict]) -> dict:
        """
        合并多段结果并去重
        :param segment_results: 各段的编译结果
        :return: 合并后的 CandidatePackage
        """
        all_candidates = []
        all_risks = []
        all_actions = []
        all_questions = []
        raw_outputs = []

        for result in segment_results:
            all_candidates.extend(result.get("candidates", []))
            all_risks.extend(result.get("risks", []))
            all_actions.extend(result.get("action_items", []))
            all_questions.extend(result.get("open_questions", []))
            if result.get("raw_output"):
                raw_outputs.append(result["raw_output"])

        # 简单去重：基于标题相似度
        unique_candidates = self._deduplicate_candidates(all_candidates)
        unique_risks = self._deduplicate_by_title(all_risks)
        unique_actions = self._deduplicate_by_title(all_actions)
        unique_questions = self._deduplicate_by_title(all_questions)

        return {
            "candidates": unique_candidates,
            "risks": unique_risks,
            "action_items": unique_actions,
            "open_questions": unique_questions,
            "raw_output": "\n---\n".join(raw_outputs) if raw_outputs else None,
        }

    def _deduplicate_candidates(self, candidates: list) -> list:
        """候选决策去重"""
        seen = set()
        unique = []

        for cand in candidates:
            title = cand.get("title", "").strip()
            if not title:
                continue

            # 简单的标题归一化
            key = re.sub(r'[\s，。、！？：；""''()（）【】\[\].,!?;:\'"]', '', title).lower()

            if key in seen:
                continue

            seen.add(key)
            unique.append(cand)

        return unique

    def _deduplicate_by_title(self, items: list) -> list:
        """按标题去重"""
        seen = set()
        unique = []

        for item in items:
            title = item.get("title", "") if isinstance(item, dict) else str(item)
            key = re.sub(r'[\s，。、！？：；""''()（）【】\[\].,!?;:\'"]', '', title).lower()

            if key in seen:
                continue

            seen.add(key)
            unique.append(item)

        return unique

    def _rule_validate(self, candidate_package: dict) -> dict:
        """
        规则二次校验
        :param candidate_package: 候选包
        :return: 校验后的候选包
        """
        if "candidates" not in candidate_package or not isinstance(candidate_package["candidates"], list):
            raise ValueError("Aily 输出缺少合法 candidates 数组")

        validated_candidates = []

        for cand in candidate_package["candidates"]:
            # 校验必填字段
            if not cand.get("candidate_id"):
                cand["candidate_id"] = generate_id("cand")

            if not cand.get("type"):
                cand["type"] = "conclusion"

            if not cand.get("title"):
                continue  # 没有标题的跳过

            if "confidence" not in cand:
                cand["confidence"] = 0.7

            # experiment_ref 格式确定性校验（real/mock 共用，PRD：编号由确定性规则控制）
            exp_ref = cand.get("experiment_ref", "")
            if exp_ref and not re.match(r'^[A-Za-z][A-Za-z0-9_\-]*$', str(exp_ref)):
                cand["_validation_warning"] = f"experiment_ref 格式异常：{exp_ref}"

            if not cand.get("evidence"):
                cand["evidence"] = []

            # 无条件强制候选边界：Aily 只能产候选，防 status=approved/needs_review=False 越权发布
            cand["status"] = "candidate"
            cand["needs_review"] = True

            # 校验参数格式
            params = cand.get("parameters", [])
            for param in params:
                if not param.get("name"):
                    continue
                # 数值参数尝试提取单位
                if param.get("value") and not param.get("unit"):
                    extracted = self._extract_unit(param["value"])
                    if extracted:
                        param["value"] = extracted["value"]
                        param["unit"] = extracted["unit"]

            validated_candidates.append(cand)

        candidate_package["candidates"] = validated_candidates
        return candidate_package

    def _extract_unit(self, value_str: str) -> Optional[dict]:
        """从字符串中提取数值和单位"""
        patterns = [
            r'^(\d+\.?\d*)\s*(℃|摄氏度|度)$',
            r'^(\d+\.?\d*)\s*(分钟|min|minute)$',
            r'^(\d+\.?\d*)\s*(小时|h|hour)$',
            r'^(\d+\.?\d*)\s*(%|百分比)$',
            r'^(\d+\.?\d*)\s*(ml|毫升)$',
            r'^(\d+\.?\d*)\s*(g|克)$',
        ]

        for pattern in patterns:
            match = re.match(pattern, value_str.strip())
            if match:
                return {
                    "value": match.group(1),
                    "unit": match.group(2),
                }

        return None

    # ==================== Mock 实现 ====================

    def _mock_compile(self, meeting_package: dict) -> dict:
        """Mock 编译：基于规则生成示例候选决策"""
        mock_file = self.mock_data_dir / "sample_aily_output.json"
        if mock_file.exists():
            with open(mock_file, "r", encoding="utf-8") as f:
                return json.load(f)

        # 基于会议内容生成示例候选
        transcript = meeting_package.get("content", {}).get("transcript", [])
        summary = meeting_package.get("content", {}).get("summary", "")
        title = meeting_package.get("title", "未命名会议")

        # 识别实验编号
        experiment_ref = self._extract_experiment_ref(transcript)

        candidates = []

        # 识别决策
        decision_keywords = ["决定", "就这么定", "通过", "采用", "同意", "定了", "就按这个", "那就"]
        for item in transcript:
            text = item.get("text", "")
            if any(kw in text for kw in decision_keywords) and len(text) > 10:
                candidates.append({
                    "candidate_id": generate_id("cand"),
                    "type": "decision",
                    "title": self._extract_decision_title(text),
                    "description": text,
                    "experiment_ref": experiment_ref,
                    "parameters": self._extract_parameters(text),
                    "confidence": 0.85,
                    "evidence": [
                        {
                            "speaker": item.get("speaker", ""),
                            "start_offset_sec": item.get("start_offset_sec", 0),
                            "end_offset_sec": item.get("end_offset_sec", 0),
                            "text": text,
                            "source_url": meeting_package.get("source_url", ""),
                        }
                    ],
                    "status": "candidate",
                    "needs_review": True,
                })

        # 识别参数变更
        param_change_keywords = ["调整", "改成", "改为", "从.*到", "从.*到", "提升", "降低", "增加", "减少"]
        for item in transcript:
            text = item.get("text", "")
            if any(kw in text for kw in ["温度", "时间", "浓度", "压力", "速度"]) and any(kw in text for kw in param_change_keywords):
                params = self._extract_parameters(text)
                if params:
                    candidates.append({
                        "candidate_id": generate_id("cand"),
                        "type": "parameter_change",
                        "title": f"参数调整：{params[0]['name']}",
                        "description": text,
                        "experiment_ref": experiment_ref,
                        "parameters": params,
                        "confidence": 0.8,
                        "evidence": [
                            {
                                "speaker": item.get("speaker", ""),
                                "start_offset_sec": item.get("start_offset_sec", 0),
                                "end_offset_sec": item.get("end_offset_sec", 0),
                                "text": text,
                                "source_url": meeting_package.get("source_url", ""),
                            }
                        ],
                        "status": "candidate",
                        "needs_review": True,
                    })

        # 识别风险/顾虑
        risks = []
        risk_keywords = ["顾虑", "担心", "风险", "问题", "会不会", "有没有可能", "隐患", "副作用"]
        for item in transcript:
            text = item.get("text", "")
            if any(kw in text for kw in risk_keywords) and len(text) > 10:
                risks.append({
                    "title": self._extract_risk_title(text),
                    "description": text,
                    "raised_by": item.get("speaker", ""),
                    "severity": "medium",
                })

        # 识别行动项
        action_items = []
        action_keywords = ["负责", "安排", "跟进", "你来", "我来", "交给", "下周三", "这周", "明天"]
        for item in transcript:
            text = item.get("text", "")
            if any(kw in text for kw in action_keywords) and len(text) > 10:
                action_items.append({
                    "title": self._extract_action_title(text),
                    "description": text,
                    "assignee": item.get("speaker", ""),
                    "source": "meeting_transcript",
                })

        # 去重
        candidates = self._deduplicate_candidates(candidates)
        risks = self._deduplicate_by_title(risks)
        action_items = self._deduplicate_by_title(action_items)

        # 如果没有识别到任何候选，添加一个总结型的
        if not candidates:
            candidates.append({
                "candidate_id": generate_id("cand"),
                "type": "conclusion",
                "title": f"会议总结：{title}",
                "description": summary or "本次会议讨论了相关议题",
                "experiment_ref": experiment_ref,
                "confidence": 0.7,
                "evidence": [],
                "status": "candidate",
                "needs_review": True,
            })

        return {
            "candidates": candidates,
            "risks": risks,
            "action_items": action_items,
            "open_questions": [],
            "raw_output": json.dumps({"candidates_count": len(candidates)}, ensure_ascii=False),
        }

    def _extract_experiment_ref(self, transcript: list) -> str:
        """提取实验编号"""
        pattern = r'EXP[-_]?\d{4}[-_]?\d{3}|实验\s*[#№]?\s*\d+'
        for item in transcript:
            text = item.get("text", "")
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return match.group(0)
        return ""

    def _extract_decision_title(self, text: str) -> str:
        """提取决策标题"""
        # 简单截取：取"决定"、"采用"等关键词后面的内容
        for kw in ["决定", "采用", "同意", "就这么定", "那就"]:
            idx = text.find(kw)
            if idx >= 0:
                title = text[idx + len(kw):].strip("，。、！？：； ")
                if len(title) > 5:
                    return title[:30] + ("..." if len(title) > 30 else "")
        return text[:30] + "..."

    def _extract_risk_title(self, text: str) -> str:
        """提取风险标题"""
        for kw in ["顾虑", "担心", "风险", "问题"]:
            idx = text.find(kw)
            if idx >= 0:
                title = text[idx:].strip("，。、！？：； ")
                if len(title) > 3:
                    return title[:25] + ("..." if len(title) > 25 else "")
        return text[:25] + "..."

    def _extract_action_title(self, text: str) -> str:
        """提取行动项标题"""
        # 简单处理
        return text[:30] + ("..." if len(text) > 30 else "")

    def _extract_parameters(self, text: str) -> list:
        """从文本中提取参数"""
        params = []

        # 温度
        temp_match = re.search(r'(\d+\.?\d*)\s*(度|℃|摄氏度)', text)
        if temp_match:
            params.append({
                "name": "温度",
                "value": temp_match.group(1),
                "unit": temp_match.group(2),
            })

        # 时间
        time_match = re.search(r'(\d+)\s*(分钟|min|小时|h)', text)
        if time_match:
            params.append({
                "name": "时间",
                "value": time_match.group(1),
                "unit": time_match.group(2),
            })

        # 百分比
        pct_match = re.search(r'(\d+\.?\d*)\s*%', text)
        if pct_match:
            params.append({
                "name": "比例",
                "value": pct_match.group(1),
                "unit": "%",
            })

        return params

    # ==================== 真实实现 ====================

    @with_retry(interface_name="aily.compile")
    def _real_compile(self, meeting_package: dict) -> dict:
        """真实调用 Aily Skill 编译"""
        # 分段处理
        segments = self._segment_meeting(meeting_package)

        segment_results = []
        for i, segment in enumerate(segments):
            result = self._call_skill(segment, segment_index=i, total_segments=len(segments))
            segment_results.append(result)

        # 合并去重
        merged = self._merge_and_dedup(segment_results)
        return merged

    def _call_skill(self, segment: dict, segment_index: int = 0, total_segments: int = 1) -> dict:
        """
        调用单个 Aily Skill
        """
        # 构造 Prompt
        prompt = self._build_prompt(segment, segment_index, total_segments)

        try:
            # 方式1：通过 aily CLI 调用
            cmd = [
                "aily", "skill", "run",
                "--skill-id", self.skill_id,
                "--input", json.dumps({"prompt": prompt}, ensure_ascii=False),
            ]

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=120
            )

            if result.returncode != 0:
                raise Exception(f"aily CLI 执行失败: {result.stderr}")

            output = json.loads(result.stdout)
            return self._parse_skill_output(output)

        except FileNotFoundError:
            # 方式2：通过 HTTP API 调用
            return self._call_skill_api(prompt)
        except subprocess.TimeoutExpired:
            raise Exception("Aily Skill 调用超时")
        except json.JSONDecodeError:
            raise Exception("解析 Aily Skill 输出失败")

    def _call_skill_api(self, prompt: str) -> dict:
        """通过 HTTP API 调用 Aily Skill"""
        import urllib.request
        import urllib.error

        url = f"{self.api_base}/v1/skills/{self.skill_id}/run"
        data = json.dumps({"prompt": prompt}).encode("utf-8")

        req = urllib.request.Request(
            url,
            data=data,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {Config.AILY_API_KEY}",
            },
            method="POST"
        )

        try:
            with urllib.request.urlopen(req, timeout=120) as response:
                result = json.loads(response.read().decode("utf-8"))
                return self._parse_skill_output(result)
        except urllib.error.URLError as e:
            raise Exception(f"Aily API 调用失败: {e}")

    def _build_prompt(self, segment: dict, segment_index: int, total_segments: int) -> str:
        """构建 Prompt"""
        transcript_text = ""
        for item in segment.get("transcript", []):
            time_str = seconds_to_hms(item.get("start_offset_sec", 0))
            speaker = item.get("speaker", "未知")
            text = item.get("text", "")
            transcript_text += f"[{time_str}] {speaker}: {text}\n"

        chapter = segment.get("chapter", "")
        start_time = seconds_to_hms(segment.get("start_offset", 0))
        end_time = seconds_to_hms(segment.get("end_offset", 0))

        prompt = f"""
你是一个会议决策提取助手。请从以下会议内容中提取结构化的决策、结论、风险、行动项和参数变更。

会议信息：
- 章节：{chapter}
- 时间段：{start_time} - {end_time}
- 这是第 {segment_index + 1}/{total_segments} 段

会议内容：
{transcript_text}

请按以下 JSON 格式输出（不要输出其他内容）：
{{
  "candidates": [
    {{
      "type": "decision|conclusion|risk|action_item|question|parameter_change",
      "title": "简短标题",
      "description": "详细描述",
      "experiment_ref": "关联的实验编号（如有）",
      "parameters": [
        {{"name": "参数名", "value": "数值", "unit": "单位"}}
      ],
      "confidence": 0.0-1.0,
      "evidence": [
        {{
          "speaker": "说话人",
          "start_offset_sec": 开始时间秒,
          "end_offset_sec": 结束时间秒,
          "text": "原文"
        }}
      ],
      "needs_review": true
    }}
  ],
  "risks": [
    {{"title": "风险标题", "description": "描述", "raised_by": "提出人"}}
  ],
  "action_items": [
    {{"title": "行动项", "description": "描述", "assignee": "负责人"}}
  ],
  "open_questions": [
    {{"title": "问题", "description": "描述"}}
  ]
}}

要求：
1. 只提取明确提到的内容，不要编造
2. 每个候选都要有证据支撑
3. 置信度要客观评估
4. 参数变更要明确提取参数名、数值和单位
5. 输出必须是合法的 JSON
"""
        return prompt.strip()

    def _parse_skill_output(self, output: dict) -> dict:
        """解析 Skill 输出"""
        # 尝试从不同字段获取文本
        text = (
            output.get("output")
            or output.get("result")
            or output.get("content")
            or output.get("text")
            or ""
        )

        if isinstance(text, dict):
            # 已经是结构化的
            return text

        # 从文本中提取 JSON
        return self._extract_json_from_text(str(text))

    def _extract_json_from_text(self, text: str) -> dict:
        """从文本中提取 JSON"""
        # 尝试直接解析
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # 尝试找第一个 { 和最后一个 }
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            try:
                return json.loads(text[start:end + 1])
            except json.JSONDecodeError:
                pass

        # 尝试用正则找 JSON 块
        import re
        json_pattern = r'\{[\s\S]*\}'
        match = re.search(json_pattern, text)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                pass

        # 解析失败必须显式失败，不能把外部错误伪装成合法的空候选包。
        raise ValueError("Aily 输出不是合法 JSON 结构")


# 单例
aily_adapter = AilyAdapter()
