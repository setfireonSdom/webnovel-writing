"""
节奏检查器 (Pacing Checker)
职责：Strand Weave 节奏分析

三线比例：
- Quest（主线）：55-65%
- Fire（感情线）：20-30%
- Constellation（世界观线）：10-20%

警告阈值：
- 主线过载：连续 5+ 章
- 感情线干旱：>10 章
- 世界观线缺失：>15 章
"""

import logging
import re
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field

from ...llm.base import BaseLLM
from ...data.state_manager import StateManager
from .consistency_checker import Issue, CheckResult

logger = logging.getLogger(__name__)


class PacingChecker:
    """节奏分析检查器"""

    def __init__(self, llm: BaseLLM, state_manager: StateManager):
        self.llm = llm
        self.state_manager = state_manager
        self.issue_counter = 0

    async def check(
        self,
        chapter_num: int,
        content: str,
        recent_strands: Optional[List[Dict]] = None,
    ) -> CheckResult:
        """执行节奏检查"""
        issues = []
        self.issue_counter = 0

        # 1. 识别本章情节线类型
        strand_type = await self._identify_strand(chapter_num, content)

        # 2. 分析三线比例（如果有历史数据）
        if recent_strands:
            issues.extend(self._analyze_strand_ratio(chapter_num, strand_type, recent_strands))

        # 3. 检查节奏问题
        issues.extend(self._check_pacing(chapter_num, strand_type, recent_strands))

        score = self._calculate_score(issues)
        summary = self._generate_summary(strand_type, issues)

        return CheckResult(
            checker="pacing",
            score=score,
            issues=issues,
            summary=summary,
        )

    async def _identify_strand(self, chapter_num: int, content: str) -> str:
        """识别本章情节线类型"""
        prompt = f"""
你是情节线类型分析员。请判断本章主要属于哪种情节线。

## 情节线类型说明
1. quest（主线）：主角的核心目标/任务推进，如修炼、升级、战斗、完成任务
2. fire（感情线）：角色之间的感情发展，如恋爱、友情、师徒情
3. constellation（世界观线）：世界观展开、势力介绍、背景设定

## 章节内容
{content[:4000]}

请判断主要情节线类型，可以有多个但需要标注主次比例。

输出 JSON 格式：
{{
  "primary": "quest|fire|constellation",
  "mix": {{
    "quest": 0.6,
    "fire": 0.3,
    "constellation": 0.1
  }},
  "description": "简述本章主要情节"
}}
"""
        try:
            response = await self.llm.generate(
                prompt=prompt,
                system_prompt="你是情节线类型分析员。",
                temperature=0.2,
                max_tokens=512,
            )

            import json
            json_match = re.search(r'\{.*\}', response.text, re.DOTALL)
            if json_match:
                result = json.loads(json_match.group())
                return result.get("primary", "quest")
        except Exception as e:
            logger.warning(f"情节线类型识别失败: {e}")

        return "quest"

    def _analyze_strand_ratio(
        self,
        chapter_num: int,
        current_strand: str,
        recent_strands: List[Dict],
    ) -> List[Issue]:
        """分析三线比例"""
        issues = []

        # 统计最近章节的比例
        total = len(recent_strands) + 1  # 加上本章
        strand_counts = {"quest": 0, "fire": 0, "constellation": 0}

        for strand in recent_strands[-20:]:  # 最近 20 章
            strand_type = strand.get("strand_type", "quest")
            strand_counts[strand_type] = strand_counts.get(strand_type, 0) + 1

        strand_counts[current_strand] += 1

        # 计算比例
        quest_ratio = strand_counts["quest"] / total
        fire_ratio = strand_counts["fire"] / total
        constellation_ratio = strand_counts["constellation"] / total

        # 检查比例是否合理
        # Quest 主线：55-65%
        if quest_ratio > 0.75:
            self.issue_counter += 1
            issues.append(Issue(
                id=f"PACING-{self.issue_counter:03d}",
                severity="medium",
                category="strand_ratio_quest_overload",
                description=f"主线占比过高 ({quest_ratio:.0%})，缺少感情线和世界观线",
                suggestion="适当添加感情线或世界观线，丰富故事层次",
            ))
        elif quest_ratio < 0.40:
            self.issue_counter += 1
            issues.append(Issue(
                id=f"PACING-{self.issue_counter:03d}",
                severity="high",
                category="strand_ratio_quest_underload",
                description=f"主线占比过低 ({quest_ratio:.0%})，故事偏离主线",
                suggestion="增加主线情节，确保故事有清晰的推进方向",
            ))

        # Fire 感情线：20-30%
        if fire_ratio < 0.10 and total > 10:
            self.issue_counter += 1
            issues.append(Issue(
                id=f"PACING-{self.issue_counter:03d}",
                severity="medium",
                category="strand_ratio_fire_drought",
                description=f"感情线占比过低 ({fire_ratio:.0%})，可能存在感情线干旱",
                suggestion="适当添加感情线情节",
            ))

        return issues

    def _check_pacing(
        self,
        chapter_num: int,
        current_strand: str,
        recent_strands: Optional[List[Dict]],
    ) -> List[Issue]:
        """检查节奏问题"""
        issues = []

        if not recent_strands:
            return issues

        # 检查连续同类型情节线
        consecutive_count = 0
        for strand in reversed(recent_strands[-15:]):
            if strand.get("strand_type") == current_strand:
                consecutive_count += 1
            else:
                break

        # 警告阈值
        if current_strand == "quest" and consecutive_count >= 5:
            self.issue_counter += 1
            issues.append(Issue(
                id=f"PACING-{self.issue_counter:03d}",
                severity="high",
                category="pacing_quest_streak",
                description=f"主线连续 {consecutive_count + 1} 章，可能导致读者疲劳",
                suggestion="插入感情线或世界观线情节，调节节奏",
            ))

        # 感情线超过 10 章未出现
        last_fire_index = None
        for i, strand in enumerate(reversed(recent_strands[-15:])):
            if strand.get("strand_type") == "fire":
                last_fire_index = i
                break

        if last_fire_index is None and len(recent_strands) >= 10:
            self.issue_counter += 1
            issues.append(Issue(
                id=f"PACING-{self.issue_counter:03d}",
                severity="high",
                category="pacing_fire_absent",
                description=f"感情线已超过 10 章未出现",
                suggestion="尽快安排感情线情节",
            ))

        # 世界观线超过 15 章未出现
        last_constellation_index = None
        for i, strand in enumerate(reversed(recent_strands[-20:])):
            if strand.get("strand_type") == "constellation":
                last_constellation_index = i
                break

        if last_constellation_index is None and len(recent_strands) >= 15:
            self.issue_counter += 1
            issues.append(Issue(
                id=f"PACING-{self.issue_counter:03d}",
                severity="medium",
                category="pacing_constellation_absent",
                description=f"世界观线已超过 15 章未出现",
                suggestion="适当展开世界观，介绍新势力或设定",
            ))

        return issues

    def _calculate_score(self, issues: List[Issue]) -> int:
        """计算节奏得分"""
        score = 100
        for issue in issues:
            if issue.severity == "high":
                score -= 20
            elif issue.severity == "medium":
                score -= 10
            else:
                score -= 5
        return max(0, score)

    def _generate_summary(self, strand_type: str, issues: List[Issue]) -> str:
        """生成检查总结"""
        strand_names = {
            "quest": "主线",
            "fire": "感情线",
            "constellation": "世界观线",
        }
        strand_name = strand_names.get(strand_type, "未知")

        if not issues:
            return f"节奏检查通过。本章主要为{strand_name}情节，节奏合理。"

        high = sum(1 for i in issues if i.severity == "high")
        medium = sum(1 for i in issues if i.severity == "medium")
        low = sum(1 for i in issues if i.severity == "low")

        summary = f"本章主要为{strand_name}情节。节奏检查发现 {len(issues)} 个问题："
        if high > 0:
            summary += f"\n- 高优先级: {high} 个"
        if medium > 0:
            summary += f"\n- 中优先级: {medium} 个"
        if low > 0:
            summary += f"\n- 低优先级: {low} 个"

        return summary
