"""
爽点检查器 (High Point Checker)
职责：爽点密度和质量分析

8 种执行模式：
- 装逼打脸、扮猪吃虎、越级反杀、打脸权威
- 反派翻车、甜蜜超预期、迪化误解、身份掉马

密度基线：
- 每章：至少 1 个爽点
- 每 5 章：组合爽点
- 每 10-15 章：里程碑爽点

反单调：单一类型不超过 80%
"""

import logging
import re
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field

from ...llm.base import BaseLLM
from ...data.state_manager import StateManager
from .consistency_checker import Issue, CheckResult

logger = logging.getLogger(__name__)

# 爽点类型
COOL_POINT_TYPES = [
    "装逼打脸",
    "扮猪吃虎",
    "越级反杀",
    "打脸权威",
    "反派翻车",
    "甜蜜超预期",
    "迪化误解",
    "身份掉马",
]


class HighPointChecker:
    """爽点密度和质量检查器"""

    def __init__(self, llm: BaseLLM, state_manager: StateManager):
        self.llm = llm
        self.state_manager = state_manager
        self.issue_counter = 0

    async def check(
        self,
        chapter_num: int,
        content: str,
        recent_chapters: Optional[List[Dict]] = None,
    ) -> CheckResult:
        """执行爽点检查"""
        issues = []
        self.issue_counter = 0

        # 1. 识别本章爽点
        cool_points = await self._identify_cool_points(chapter_num, content)

        # 2. 密度检查
        issues.extend(self._check_density(chapter_num, len(cool_points), cool_points))

        # 3. 质量检查
        issues.extend(await self._check_quality(chapter_num, content, cool_points))

        # 4. 反单调检查（如果有历史数据）
        if recent_chapters:
            issues.extend(self._check_anti_monotony(chapter_num, cool_points, recent_chapters))

        score = self._calculate_score(issues, len(cool_points))
        summary = self._generate_summary(cool_points, issues)

        return CheckResult(
            checker="high_point",
            score=score,
            issues=issues,
            summary=summary,
        )

    async def _identify_cool_points(self, chapter_num: int, content: str) -> List[Dict[str, Any]]:
        """识别本章爽点"""
        prompt = f"""
你是爽点分析专家。请识别以下章节中的所有爽点。

## 爽点类型说明
1. 装逼打脸：主角展示实力，让看不起他的人被打脸
2. 扮猪吃虎：主角隐藏实力，关键时刻出手震惊众人
3. 越级反杀：主角以弱胜强，越级击败对手
4. 打脸权威：主角打脸权威人士或组织
5. 反派翻车：反派自以为是却栽跟头
6. 甜蜜超预期：感情线超预期发展
7. 迪化误解：角色因为误解而产生有趣/爽的结果
8. 身份掉马：主角隐藏身份被揭露，震惊众人

## 章节内容
{content[:5000]}

请识别所有爽点，输出 JSON 格式：
[
  {{
    "type": "爽点类型",
    "intensity": "low|medium|high|explosive",
    "description": "简述",
    "location": "位置"
  }}
]
"""
        try:
            response = await self.llm.generate(
                prompt=prompt,
                system_prompt="你是爽点分析专家。",
                temperature=0.3,
                max_tokens=1024,
            )

            import json
            json_match = re.search(r'\[.*\]', response.text, re.DOTALL)
            if json_match:
                cool_points = json.loads(json_match.group())
                return cool_points
        except Exception as e:
            logger.warning(f"爽点识别失败: {e}")

        return []

    def _check_density(
        self,
        chapter_num: int,
        count: int,
        cool_points: List[Dict],
    ) -> List[Issue]:
        """检查爽点密度"""
        issues = []

        # 基线：每章至少 1 个爽点
        if count == 0:
            self.issue_counter += 1
            issues.append(Issue(
                id=f"HP-{self.issue_counter:03d}",
                severity="high",
                category="cool_point_density",
                description="本章无任何爽点，读者可能流失",
                suggestion="添加至少一个爽点情节",
            ))
        elif count == 1:
            # 1 个爽点可以接受
            pass
        elif count >= 3:
            # 爽点过多，可能过于密集
            self.issue_counter += 1
            issues.append(Issue(
                id=f"HP-{self.issue_counter:03d}",
                severity="low",
                category="cool_point_density",
                description=f"本章有 {count} 个爽点，密度过高，可能让读者疲劳",
                suggestion="适当减少爽点数量，提高单个质量",
            ))

        return issues

    async def _check_quality(
        self,
        chapter_num: int,
        content: str,
        cool_points: List[Dict],
    ) -> List[Issue]:
        """检查爽点质量"""
        issues = []

        if not cool_points:
            return issues

        prompt = f"""
你是爽点质量评估员。请评估以下章节中爽点的质量。

## 识别到的爽点
{cool_points}

## 章节内容
{content[:4000]}

请评估：
1. 爽点是否有足够的铺垫？（没有铺垫的爽点效果差）
2. 爽点的释放是否自然？（是否过于刻意）
3. 爽点的强度是否与章节位置匹配？（开篇应该弱一些，高潮章节应该强）
4. 是否有"为爽而爽"的问题？

输出 JSON 格式：
[
  {{
    "severity": "high|medium|low",
    "description": "问题描述",
    "suggestion": "修复建议"
  }}
]
"""
        try:
            response = await self.llm.generate(
                prompt=prompt,
                system_prompt="你是爽点质量评估员。",
                temperature=0.3,
                max_tokens=1024,
            )

            import json
            json_match = re.search(r'\[.*\]', response.text, re.DOTALL)
            if json_match:
                problems = json.loads(json_match.group())
                for p in problems:
                    self.issue_counter += 1
                    issues.append(Issue(
                        id=f"HP-{self.issue_counter:03d}",
                        severity=p.get("severity", "medium"),
                        category="cool_point_quality",
                        description=p.get("description", ""),
                        suggestion=p.get("suggestion", ""),
                    ))
        except Exception as e:
            logger.warning(f"爽点质量检查失败: {e}")

        return issues

    def _check_anti_monotony(
        self,
        chapter_num: int,
        cool_points: List[Dict],
        recent_chapters: List[Dict],
    ) -> List[Issue]:
        """反单调检查"""
        issues = []

        # 统计最近章节的爽点类型分布
        type_counts = {}
        for chapter in recent_chapters[-10:]:  # 最近 10 章
            for cp in chapter.get("cool_points", []):
                cp_type = cp.get("type", "unknown")
                type_counts[cp_type] = type_counts.get(cp_type, 0) + 1

        # 加上本章
        for cp in cool_points:
            cp_type = cp.get("type", "unknown")
            type_counts[cp_type] = type_counts.get(cp_type, 0) + 1

        total = sum(type_counts.values())
        if total == 0:
            return issues

        # 检查单一类型是否超过 80%
        for cp_type, count in type_counts.items():
            ratio = count / total
            if ratio > 0.8 and total >= 5:
                self.issue_counter += 1
                issues.append(Issue(
                    id=f"HP-{self.issue_counter:03d}",
                    severity="medium",
                    category="cool_point_monotony",
                    description=f"最近章节【{cp_type}】类型占比 {ratio:.0%}，过于单一",
                    suggestion="尝试使用其他类型的爽点，丰富阅读体验",
                ))

        return issues

    def _calculate_score(self, issues: List[Issue], cool_point_count: int) -> int:
        """计算爽点得分"""
        score = 100

        # 有爽点加分
        if cool_point_count >= 1:
            score += min(cool_point_count * 5, 20)

        # 问题扣分
        for issue in issues:
            if issue.severity == "high":
                score -= 20
            elif issue.severity == "medium":
                score -= 10
            else:
                score -= 5

        return max(0, min(100, score))  # 最高 100 分，与其他审查器保持一致

    def _generate_summary(self, cool_points: List[Dict], issues: List[Issue]) -> str:
        """生成检查总结"""
        if not cool_points:
            return "本章无爽点，建议添加至少一个爽点情节。"

        types = [cp.get("type", "未知") for cp in cool_points]
        summary = f"本章识别到 {len(cool_points)} 个爽点：{', '.join(types)}"

        if issues:
            high = sum(1 for i in issues if i.severity == "high")
            if high > 0:
                summary += f"\n发现 {high} 个高优先级问题，建议修复"

        return summary
