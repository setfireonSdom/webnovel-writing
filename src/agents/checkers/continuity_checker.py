"""
连贯性检查器
职责：叙事流畅度、场景转换、情节线、伏笔、逻辑

检查层级：
1. 场景转换流畅度（评级 A/B/C/F）
2. 情节线连贯性（追踪活跃/休眠/被遗忘的线索）
3. 伏笔管理（短期 1-3 章、中期 4-10 章、长期 10+ 章）
4. 逻辑流（因果关系、矛盾检测）
"""

import logging
import re
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field

from ...llm.base import BaseLLM
from ...data.state_manager import StateManager
from .consistency_checker import Issue, CheckResult

logger = logging.getLogger(__name__)


class ContinuityChecker:
    """叙事连贯性检查器"""

    def __init__(self, llm: BaseLLM, state_manager: StateManager):
        self.llm = llm
        self.state_manager = state_manager
        self.issue_counter = 0

    async def check(
        self,
        chapter_num: int,
        content: str,
        previous_summary: str = "",
        outline: Optional[Dict] = None,
    ) -> CheckResult:
        """执行连贯性检查"""
        issues = []
        self.issue_counter = 0

        # 1. 场景转换检查
        issues.extend(await self._check_scene_transitions(chapter_num, content))

        # 2. 情节线连贯性检查
        issues.extend(await self._check_plot_continuity(chapter_num, content, previous_summary))

        # 3. 伏笔管理检查
        issues.extend(await self._check_foreshadowing(chapter_num, content))

        # 4. 逻辑流检查
        issues.extend(await self._check_logic_flow(chapter_num, content))

        score = self._calculate_score(issues)
        summary = self._generate_summary(issues)

        return CheckResult(
            checker="continuity",
            score=score,
            issues=issues,
            summary=summary,
        )

    async def _check_scene_transitions(self, chapter_num: int, content: str) -> List[Issue]:
        """场景转换流畅度检查"""
        issues = []

        prompt = f"""
你是叙事流畅度检查员。请评估以下章节的场景转换质量。

## 章节内容
{content[:4000]}

请评估：
1. 场景之间是否有清晰的过渡？（时间/地点/视角转换是否有提示）
2. 是否有突兀的场景切换？
3. 视角转换是否自然？（如从A角色视角转到B角色视角）
4. 转换评级：A（丝滑）、B（自然）、C（生硬但有标记）、F（混乱无标记）

输出 JSON 格式：
{{
  "rating": "A|B|C|F",
  "issues": [
    {{
      "severity": "high|medium|low",
      "description": "问题描述",
      "location": "位置",
      "suggestion": "修复建议"
    }}
  ]
}}
"""
        try:
            response = await self.llm.generate(
                prompt=prompt,
                system_prompt="你是叙事流畅度和场景转换检查员。",
                temperature=0.2,
                max_tokens=1024,
            )

            import json
            json_match = re.search(r'\{.*\}', response.text, re.DOTALL)
            if json_match:
                result = json.loads(json_match.group())
                rating = result.get("rating", "B")
                
                # F 级转换为 high 问题
                if rating == "F":
                    self.issue_counter += 1
                    issues.append(Issue(
                        id=f"CONT-{self.issue_counter:03d}",
                        severity="high",
                        category="scene_transition",
                        description="场景转换混乱，缺乏必要的过渡标记",
                        suggestion="添加时间/地点/视角转换提示",
                    ))

                for p in result.get("issues", []):
                    self.issue_counter += 1
                    issues.append(Issue(
                        id=f"CONT-{self.issue_counter:03d}",
                        severity=p.get("severity", "medium"),
                        category="scene_transition",
                        description=p.get("description", ""),
                        location=p.get("location", ""),
                        suggestion=p.get("suggestion", ""),
                    ))
        except Exception as e:
            logger.warning(f"场景转换检查失败: {e}")

        return issues

    async def _check_plot_continuity(
        self,
        chapter_num: int,
        content: str,
        previous_summary: str,
    ) -> List[Issue]:
        """情节线连贯性检查"""
        issues = []

        prompt = f"""
你是情节线连贯性检查员。请检查以下章节的情节是否连贯。

## 前情摘要
{previous_summary}

## 本章内容（前4000字）
{content[:4000]}

请检查：
1. 本章开头是否承接了前情？
2. 是否有情节线突然中断或消失？
3. 是否有新的情节线引入？是否需要铺垫？
4. 是否有伏笔被遗忘？（超过10章未回收的伏笔）

输出 JSON 格式：
[
  {{
    "severity": "high|medium|low",
    "description": "问题描述",
    "location": "位置",
    "suggestion": "修复建议"
  }}
]
"""
        try:
            response = await self.llm.generate(
                prompt=prompt,
                system_prompt="你是情节线连贯性检查员。",
                temperature=0.2,
                max_tokens=1024,
            )

            import json
            json_match = re.search(r'\[.*\]', response.text, re.DOTALL)
            if json_match:
                problems = json.loads(json_match.group())
                for p in problems:
                    self.issue_counter += 1
                    issues.append(Issue(
                        id=f"CONT-{self.issue_counter:03d}",
                        severity=p.get("severity", "medium"),
                        category="plot_continuity",
                        description=p.get("description", ""),
                        location=p.get("location", ""),
                        suggestion=p.get("suggestion", ""),
                    ))
        except Exception as e:
            logger.warning(f"情节线连贯性检查失败: {e}")

        return issues

    async def _check_foreshadowing(self, chapter_num: int, content: str) -> List[Issue]:
        """伏笔管理检查"""
        issues = []

        prompt = f"""
你是伏笔管理检查员。请检查以下章节的伏笔设置和回收情况。

## 本章内容（前4000字）
{content[:4000]}

请检查：
1. 本章是否埋设了新伏笔？是否有标记？
2. 是否有伏笔在本章被回收？回收是否自然？
3. 是否有长期伏笔（超过10章）仍未回收？
4. 伏笔密度是否合适？（过多会让读者疲劳，过少会让故事平淡）

输出 JSON 格式：
[
  {{
    "severity": "high|medium|low",
    "type": "setup|payoff|overdue|density",
    "description": "问题描述",
    "location": "位置",
    "suggestion": "修复建议"
  }}
]
"""
        try:
            response = await self.llm.generate(
                prompt=prompt,
                system_prompt="你是伏笔管理检查员。",
                temperature=0.2,
                max_tokens=1024,
            )

            import json
            json_match = re.search(r'\[.*\]', response.text, re.DOTALL)
            if json_match:
                problems = json.loads(json_match.group())
                for p in problems:
                    self.issue_counter += 1
                    issues.append(Issue(
                        id=f"CONT-{self.issue_counter:03d}",
                        severity=p.get("severity", "medium"),
                        category=f"foreshadowing_{p.get('type', 'unknown')}",
                        description=p.get("description", ""),
                        location=p.get("location", ""),
                        suggestion=p.get("suggestion", ""),
                    ))
        except Exception as e:
            logger.warning(f"伏笔管理检查失败: {e}")

        return issues

    async def _check_logic_flow(self, chapter_num: int, content: str) -> List[Issue]:
        """逻辑流检查"""
        issues = []

        prompt = f"""
你是因果逻辑检查员。请检查以下章节的因果关系和逻辑链条。

## 本章内容（前4000字）
{content[:4000]}

请检查：
1. 事件之间是否有清晰的因果关系？
2. 角色的行为是否有合理动机？
3. 是否有矛盾的情节？（如：A角色刚死，后面又出现同名的A角色）
4. 是否有"天降神兵"式的突兀解决？（问题被未铺垫的方式解决）

输出 JSON 格式：
[
  {{
    "severity": "critical|high|medium|low",
    "description": "问题描述",
    "location": "位置",
    "suggestion": "修复建议"
  }}
]
"""
        try:
            response = await self.llm.generate(
                prompt=prompt,
                system_prompt="你是因果逻辑检查员。",
                temperature=0.2,
                max_tokens=1024,
            )

            import json
            json_match = re.search(r'\[.*\]', response.text, re.DOTALL)
            if json_match:
                problems = json.loads(json_match.group())
                for p in problems:
                    self.issue_counter += 1
                    issues.append(Issue(
                        id=f"CONT-{self.issue_counter:03d}",
                        severity=p.get("severity", "medium"),
                        category="logic_flow",
                        description=p.get("description", ""),
                        location=p.get("location", ""),
                        suggestion=p.get("suggestion", ""),
                    ))
        except Exception as e:
            logger.warning(f"逻辑流检查失败: {e}")

        return issues

    def _calculate_score(self, issues: List[Issue]) -> int:
        """计算连贯性得分"""
        score = 100
        for issue in issues:
            if issue.severity == "critical":
                score -= 30
            elif issue.severity == "high":
                score -= 20
            elif issue.severity == "medium":
                score -= 10
            else:
                score -= 5
        return max(0, score)

    def _generate_summary(self, issues: List[Issue]) -> str:
        """生成检查总结"""
        if not issues:
            return "连贯性检查通过，叙事流畅。"

        critical = sum(1 for i in issues if i.severity == "critical")
        high = sum(1 for i in issues if i.severity == "high")
        medium = sum(1 for i in issues if i.severity == "medium")
        low = sum(1 for i in issues if i.severity == "low")

        summary = f"连贯性检查发现 {len(issues)} 个问题："
        if critical > 0:
            summary += f"\n- 严重问题: {critical} 个"
        if high > 0:
            summary += f"\n- 高优先级: {high} 个"
        if medium > 0:
            summary += f"\n- 中优先级: {medium} 个"
        if low > 0:
            summary += f"\n- 低优先级: {low} 个"

        return summary
