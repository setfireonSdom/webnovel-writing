"""
追读力检查器 (Reader Pull Checker)
职责：读者吸引力评估

硬约束（必须修复，不可申诉）：
- HARD-001 可读性
- HARD-002 承诺违背
- HARD-003 节奏灾难
- HARD-004 冲突真空

软约束（可通过覆盖合约申诉）：
- 钩子强度/类型/锚点
- 微兑现数量
- 模式重复风险
- 期望过载

评分：85+ 通过，70-84 警告通过，50-69 有条件，<50 失败
"""

import logging
import re
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field

from ...llm.base import BaseLLM
from ...data.state_manager import StateManager
from .consistency_checker import Issue, CheckResult

logger = logging.getLogger(__name__)


class ReaderPullChecker:
    """追读力检查器"""

    def __init__(self, llm: BaseLLM, state_manager: StateManager):
        self.llm = llm
        self.state_manager = state_manager
        self.issue_counter = 0

    async def check(
        self,
        chapter_num: int,
        content: str,
        outline: Optional[Dict] = None,
        previous_chapters: Optional[List[str]] = None,
    ) -> CheckResult:
        """执行追读力检查"""
        issues = []
        self.issue_counter = 0

        # 1. 硬约束检查
        issues.extend(await self._check_hard_constraints(chapter_num, content))

        # 2. 软约束检查
        issues.extend(await self._check_soft_constraints(chapter_num, content, outline))

        # 3. 钩子强度评估
        hook_info = await self._evaluate_hook(chapter_num, content)

        # 4. 章末钩子检查
        ending_hook = await self._check_ending_hook(chapter_num, content)
        if ending_hook:
            issues.append(ending_hook)

        score = self._calculate_score(issues, hook_info)
        summary = self._generate_summary(score, issues, hook_info)

        return CheckResult(
            checker="reader_pull",
            score=score,
            issues=issues,
            summary=summary,
        )

    async def _check_hard_constraints(self, chapter_num: int, content: str) -> List[Issue]:
        """硬约束检查（必须修复，不可申诉）"""
        issues = []

        prompt = f"""
你是读者吸引力检查员。请检查以下章节是否存在严重的可读性问题。

## 章节内容
{content[:5000]}

## 硬约束清单
HARD-001 可读性：是否存在大量语病、错别字、句子不通顺？
HARD-002 承诺违背：是否违反了大纲中的明确承诺？
HARD-003 节奏灾难：是否整章几乎没有情节推进？
HARD-004 冲突真空：是否整章没有任何冲突（外部或内部）？

请逐项检查，输出 JSON 格式：
[
  {{
    "id": "HARD-XXX",
    "passed": true/false,
    "description": "问题描述（如果未通过）"
  }}
]
"""
        try:
            response = await self.llm.generate(
                prompt=prompt,
                system_prompt="你是读者吸引力检查员，负责检查硬约束。",
                temperature=0.2,
                max_tokens=1024,
            )

            import json
            json_match = re.search(r'\[.*\]', response.text, re.DOTALL)
            if json_match:
                results = json.loads(json_match.group())
                for r in results:
                    if not r.get("passed", True):
                        self.issue_counter += 1
                        issues.append(Issue(
                            id=r.get("id", f"HARD-{self.issue_counter:03d}"),
                            severity="critical",  # 硬约束都是 critical
                            category="hard_constraint",
                            description=r.get("description", ""),
                            suggestion="必须修复，不可申诉",
                        ))
        except Exception as e:
            logger.warning(f"硬约束检查失败: {e}")

        return issues

    async def _check_soft_constraints(
        self,
        chapter_num: int,
        content: str,
        outline: Optional[Dict],
    ) -> List[Issue]:
        """软约束检查（可通过覆盖合约申诉）"""
        issues = []

        prompt = f"""
你是读者吸引力检查员。请检查以下章节的软约束情况。

## 章节内容
{content[:5000]}

## 软约束清单
1. 钩子强度：章末钩子是否足够吸引人继续阅读？（弱/中/强）
2. 钩子类型：钩子类型是否多样化？（悬念/危机/欲望/情感/选择）
3. 微兑现数量：本章是否兑现了之前的小承诺？（至少 1 个）
4. 模式重复风险：本章结构是否与最近章节过于相似？
5. 期望过载：是否同时挖了太多坑，让读者感到混乱？

请逐项检查，输出 JSON 格式：
[
  {{
    "severity": "high|medium|low",
    "category": "hook_strength|hook_type|micro_payoff|pattern_repeat|expectation_overload",
    "description": "问题描述",
    "suggestion": "修复建议"
  }}
]
"""
        try:
            response = await self.llm.generate(
                prompt=prompt,
                system_prompt="你是读者吸引力检查员，负责检查软约束。",
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
                        id=f"READER-{self.issue_counter:03d}",
                        severity=p.get("severity", "medium"),
                        category=p.get("category", "soft_constraint"),
                        description=p.get("description", ""),
                        suggestion=p.get("suggestion", ""),
                    ))
        except Exception as e:
            logger.warning(f"软约束检查失败: {e}")

        return issues

    async def _evaluate_hook(self, chapter_num: int, content: str) -> Dict[str, Any]:
        """评估章末钩子"""
        # 提取最后 500 字
        ending = content[-500:] if len(content) > 500 else content

        prompt = f"""
你是钩子分析员。请评估以下章节结尾的钩子效果。

## 章节结尾
{ending}

请评估：
1. 钩子强度：1-100
2. 钩子类型：悬念/危机/欲望/情感/选择/反转/信息差
3. 是否有明确的钩子锚点？（让读者想知道什么？）
4. 钩子质量：是否自然？是否过于刻意？

输出 JSON 格式：
{{
  "strength": 75,
  "type": "悬念",
  "anchor": "读者想知道的问题",
  "natural": true/false,
  "description": "简述"
}}
"""
        try:
            response = await self.llm.generate(
                prompt=prompt,
                system_prompt="你是钩子分析员。",
                temperature=0.2,
                max_tokens=512,
            )

            import json
            json_match = re.search(r'\{.*\}', response.text, re.DOTALL)
            if json_match:
                return json.loads(json_match.group())
        except Exception as e:
            logger.warning(f"钩子评估失败: {e}")

        return {
            "strength": 50,
            "type": "unknown",
            "anchor": "",
            "natural": True,
            "description": "评估失败",
        }

    async def _check_ending_hook(self, chapter_num: int, content: str) -> Optional[Issue]:
        """检查章末钩子是否存在"""
        ending = content[-300:] if len(content) > 300 else content

        # 检查结尾是否是平淡的陈述句
        flat_ending_patterns = [
            r"就这[样样].*了[。！]$",
            r"于是.*就.*了[。！]$",
            r"然?后.*就.*了[。！]$",
            r"一切.*恢复.*平静[。！]$",
        ]

        for pattern in flat_ending_patterns:
            if re.search(pattern, ending):
                return Issue(
                    id=f"READER-{self.issue_counter:03d}",
                    severity="high",
                    category="ending_hook",
                    description="章节结尾过于平淡，缺乏钩子",
                    suggestion="在章节结尾设置悬念或未解决的问题",
                )

        return None

    def _calculate_score(self, issues: List[Issue], hook_info: Dict[str, Any]) -> int:
        """计算追读力得分"""
        score = 100

        # 钩子强度影响分数
        hook_strength = hook_info.get("strength", 50)
        score = int(score * 0.7 + hook_strength * 0.3)

        # 问题扣分
        for issue in issues:
            if issue.severity == "critical":
                score -= 30
            elif issue.severity == "high":
                score -= 20
            elif issue.severity == "medium":
                score -= 10
            else:
                score -= 5

        return max(0, min(100, score))

    def _generate_summary(
        self,
        score: int,
        issues: List[Issue],
        hook_info: Dict[str, Any],
    ) -> str:
        """生成检查总结"""
        # 评级
        if score >= 85:
            rating = "通过"
        elif score >= 70:
            rating = "警告通过"
        elif score >= 50:
            rating = "有条件通过"
        else:
            rating = "失败"

        hook_type = hook_info.get("type", "未知")
        hook_strength = hook_info.get("strength", 0)

        summary = f"追读力评分: {score}/100 ({rating})\n"
        summary += f"章末钩子: 强度 {hook_strength}, 类型 {hook_type}\n"

        critical = sum(1 for i in issues if i.severity == "critical")
        high = sum(1 for i in issues if i.severity == "high")

        if critical > 0:
            summary += f"\n⚠ 存在 {critical} 个硬约束问题，必须修复！"
        if high > 0:
            summary += f"\n⚠ 存在 {high} 个高优先级软约束问题"

        return summary
