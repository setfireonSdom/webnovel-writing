"""
世界观规则检查器
职责：检查章节内容是否违反世界观规则
"""

import json
import logging
import re
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field

from ...llm.base import BaseLLM
from ...data.world_rules import WorldRulesManager
from ...data.state_manager import StateManager

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


class WorldRulesChecker:
    """世界观规则检查器"""

    def __init__(self, llm: BaseLLM, world_rules_manager: WorldRulesManager, 
                 state_manager: StateManager):
        self.llm = llm
        self.world_rules_manager = world_rules_manager
        self.state_manager = state_manager
        self.issue_counter = 0

    async def check(self, chapter_num: int, content: str) -> CheckResult:
        """执行世界观规则检查"""
        issues = []
        self.issue_counter = 0
        
        # 获取活跃规则
        rules_text = self.world_rules_manager.get_rules_for_context()
        
        # 使用 LLM 检查
        prompt = f"""
你是世界观规则检查员。请严格检查以下章节是否违反了世界观规则。

## 世界观规则（必须遵守）
{rules_text}

## 章节内容
{content[:4000]}

## 检查要求
1. 力量体系：角色使用的能力是否符合境界？是否违反能力规则？
2. 地理环境：地点是否符合设定？移动是否合理？
3. 势力组织：势力行为是否符合设定？
4. 历史事件：是否与已发生的历史矛盾？
5. 物品道具：物品使用是否符合设定？
6. 其他规则：是否违反任何明确的世界观规则？

输出 JSON 格式（如无问题输出空列表）：
```json
[
  {{
    "severity": "critical|high|medium|low",
    "rule_id": "WR-XXX",
    "description": "违反了什么规则",
    "location": "大致位置",
    "suggestion": "如何修复"
  }}
]
```
"""
        try:
            response = await self.llm.generate(
                prompt=prompt,
                system_prompt="你是严格的世界观规则检查员，专门发现违反世界观设定的行为。",
                temperature=0.2,
                max_tokens=1536,
            )
            
            # 解析响应
            json_match = re.search(r'\[.*\]', response.text, re.DOTALL)
            if json_match:
                problems = json.loads(json_match.group())
                for p in problems:
                    self.issue_counter += 1
                    issues.append(Issue(
                        id=f"WRC-{self.issue_counter:03d}",
                        severity=p.get("severity", "medium"),
                        category="world_rules_violation",
                        description=f"[{p.get('rule_id', '?')}] {p.get('description', '')}",
                        location=p.get("location", ""),
                        suggestion=p.get("suggestion", ""),
                    ))
        
        except Exception as e:
            logger.warning(f"世界观规则检查失败: {e}")
        
        # 计算得分
        score = self._calculate_score(issues)
        summary = self._generate_summary(issues)
        
        return CheckResult(
            checker="world_rules",
            score=score,
            issues=issues,
            summary=summary,
        )

    def _calculate_score(self, issues: List[Issue]) -> int:
        """计算得分"""
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
        """生成总结"""
        if not issues:
            return "世界观规则检查通过，未发现违规。"
        
        critical = sum(1 for i in issues if i.severity == "critical")
        high = sum(1 for i in issues if i.severity == "high")
        medium = sum(1 for i in issues if i.severity == "medium")
        low = sum(1 for i in issues if i.severity == "low")
        
        summary = f"世界观规则检查发现 {len(issues)} 个违规："
        if critical > 0:
            summary += f"\n- 严重违规: {critical} 个"
        if high > 0:
            summary += f"\n- 高优先级: {high} 个"
        if medium > 0:
            summary += f"\n- 中优先级: {medium} 个"
        if low > 0:
            summary += f"\n- 低优先级: {low} 个"
        
        return summary
