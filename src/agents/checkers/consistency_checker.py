"""
一致性检查器
职责：设定一致性检查（"第二反幻觉定律"：设定 = 物理定律）

检查层级：
1. 能力一致性 - 验证境界/能力使用是否符合 state.json 和设定文件
2. 地点/角色一致性 - 验证移动序列和实体存在性
3. 时间线一致性 - 时间逻辑、倒计时计算、闪回标记
"""

import logging
import re
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field

from ...llm.base import BaseLLM
from ...data.state_manager import StateManager
from ...utils.file_ops import read_text_file

logger = logging.getLogger(__name__)


@dataclass
class Issue:
    """审查问题"""
    id: str
    severity: str  # critical, high, medium, low
    category: str
    description: str
    location: str = ""
    suggestion: str = ""


@dataclass
class CheckResult:
    """检查结果"""
    checker: str
    score: int
    issues: List[Issue] = field(default_factory=list)
    summary: str = ""


class ConsistencyChecker:
    """设定一致性检查器"""

    def __init__(self, llm: BaseLLM, state_manager: StateManager):
        self.llm = llm
        self.state_manager = state_manager
        self.issue_counter = 0

    async def check(self, chapter_num: int, content: str, outline: Optional[Dict] = None) -> CheckResult:
        """执行一致性检查"""
        issues = []
        self.issue_counter = 0

        state = self.state_manager.load_state()

        # 1. 能力一致性检查
        issues.extend(await self._check_ability_consistency(chapter_num, content, state))

        # 2. 地点/角色一致性检查
        issues.extend(await self._check_location_character_consistency(chapter_num, content, state))

        # 3. 时间线一致性检查
        issues.extend(await self._check_timeline_consistency(chapter_num, content))

        # 计算得分
        score = self._calculate_score(issues)

        summary = self._generate_summary(issues)

        return CheckResult(
            checker="consistency",
            score=score,
            issues=issues,
            summary=summary,
        )

    async def _check_ability_consistency(self, chapter_num: int, content: str, state) -> List[Issue]:
        """能力一致性检查"""
        issues = []

        # 构建设定上下文
        power_system = state.world.get("power_system", "")
        character_states = []
        for cs in state.character_states:
            character_states.append({
                "name": cs.name,
                "gender": cs.gender,  # 【修复】添加性别
                "cultivation": cs.cultivation,
                "status": cs.status,
                "personality": cs.personality,  # 【修复】添加性格
                "key_items": cs.key_items,
            })

        # 使用 LLM 检查能力使用是否符合设定
        prompt = f"""
你是网文设定一致性检查员。请检查以下章节是否存在能力体系矛盾。

## 力量体系
{power_system}

## 角色当前状态
{character_states}

## 章节内容（前2000字）
{content[:2000]}

请检查：
1. 角色使用的能力是否符合其当前境界？
2. 是否有越级使用能力的情况（除非有明确说明）？
3. 能力描述是否与设定矛盾？
4. 角色持有的物品是否与 state.json 一致？
5. 【关键】角色的性别代词是否正确？（男=他，女=她）

输出 JSON 格式（如无问题输出空列表）：
[
  {{
    "severity": "critical|high|medium|low",
    "description": "问题描述",
    "location": "大致位置（如：第3段）",
    "suggestion": "修复建议"
  }}
]
"""
        try:
            response = await self.llm.generate(
                prompt=prompt,
                system_prompt="你是严格的设定一致性检查员，专门发现能力体系矛盾。",
                temperature=0.2,
                max_tokens=1024,
            )

            # 解析响应
            import json
            # 尝试提取 JSON
            json_match = re.search(r'\[.*\]', response.text, re.DOTALL)
            if json_match:
                problems = json.loads(json_match.group())
                for p in problems:
                    self.issue_counter += 1
                    issues.append(Issue(
                        id=f"CONS-{self.issue_counter:03d}",
                        severity=p.get("severity", "medium"),
                        category="ability_consistency",
                        description=p.get("description", ""),
                        location=p.get("location", ""),
                        suggestion=p.get("suggestion", ""),
                    ))
        except Exception as e:
            logger.warning(f"能力一致性检查失败: {e}")

        return issues

    async def _check_location_character_consistency(self, chapter_num: int, content: str, state) -> List[Issue]:
        """地点/角色一致性检查"""
        issues = []

        # 提取现有实体
        entities = state.entities.get("all", [])
        character_names = [cs.name for cs in state.character_states]
        location_names = [e.get("name", "") for e in entities if e.get("entity_type") == "location"]

        prompt = f"""
你是网文地点/角色一致性检查员。请检查以下章节是否存在矛盾。

## 已知角色
{character_names}

## 已知地点
{location_names}

## 章节内容（前3000字）
{content[:3000]}

请检查：
1. 角色的位置移动是否合理？（如：从A地到B地是否有过渡？）
2. 是否有不存在的角色突然出现？
3. 是否有不存在的地点突然出现？
4. 角色之间的关系是否与之前矛盾？

输出 JSON 格式：
[
  {{
    "severity": "critical|high|medium|low",
    "description": "问题描述",
    "location": "大致位置",
    "suggestion": "修复建议"
  }}
]
"""
        try:
            response = await self.llm.generate(
                prompt=prompt,
                system_prompt="你是地点/角色一致性检查员。",
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
                        id=f"CONS-{self.issue_counter:03d}",
                        severity=p.get("severity", "medium"),
                        category="location_character_consistency",
                        description=p.get("description", ""),
                        location=p.get("location", ""),
                        suggestion=p.get("suggestion", ""),
                    ))
        except Exception as e:
            logger.warning(f"地点/角色一致性检查失败: {e}")

        return issues

    async def _check_timeline_consistency(self, chapter_num: int, content: str) -> List[Issue]:
        """时间线一致性检查"""
        issues = []

        prompt = f"""
你是网文时间线一致性检查员。请检查以下章节是否存在时间逻辑错误。

## 章节内容（前3000字）
{content[:3000]}

请检查：
1. 时间是否倒流？（除非明确闪回）
2. 倒计时是否跳跃？（如：从"还剩3天"突然变成"还剩1天"）
3. 大时间跨度是否有过渡标记？（如"三天后"、"数月过去"）
4. 闪回是否有明确标记？（如"回想当初"、"记忆中的画面"）

输出 JSON 格式：
[
  {{
    "severity": "critical|high|medium|low",
    "description": "问题描述",
    "location": "大致位置",
    "suggestion": "修复建议"
  }}
]
"""
        try:
            response = await self.llm.generate(
                prompt=prompt,
                system_prompt="你是时间线一致性检查员。",
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
                        id=f"CONS-{self.issue_counter:03d}",
                        severity=p.get("severity", "medium"),
                        category="timeline_consistency",
                        description=p.get("description", ""),
                        location=p.get("location", ""),
                        suggestion=p.get("suggestion", ""),
                    ))
        except Exception as e:
            logger.warning(f"时间线一致性检查失败: {e}")

        return issues

    def _calculate_score(self, issues: List[Issue]) -> int:
        """计算一致性得分"""
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
            return "设定一致性检查通过，未发现矛盾。"
        
        critical = sum(1 for i in issues if i.severity == "critical")
        high = sum(1 for i in issues if i.severity == "high")
        medium = sum(1 for i in issues if i.severity == "medium")
        low = sum(1 for i in issues if i.severity == "low")

        summary = f"设定一致性检查发现 {len(issues)} 个问题："
        if critical > 0:
            summary += f"\n- 严重问题: {critical} 个"
        if high > 0:
            summary += f"\n- 高优先级: {high} 个"
        if medium > 0:
            summary += f"\n- 中优先级: {medium} 个"
        if low > 0:
            summary += f"\n- 低优先级: {low} 个"

        return summary
