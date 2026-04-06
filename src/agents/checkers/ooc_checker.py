"""
角色偏离检查器 (OOC Checker)
职责：检测角色 Out-Of-Character 行为

三级检测：
1. 轻微偏离 - 有有效解释
2. 中度扭曲 - 无充分铺垫
3. 严重崩坏 - 完全相反，无解释
"""

import logging
import re
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field

from ...llm.base import BaseLLM
from ...data.state_manager import StateManager
from .consistency_checker import Issue, CheckResult

logger = logging.getLogger(__name__)


class OOCChecker:
    """角色偏离检查器"""

    def __init__(self, llm: BaseLLM, state_manager: StateManager):
        self.llm = llm
        self.state_manager = state_manager
        self.issue_counter = 0

    async def check(
        self,
        chapter_num: int,
        content: str,
        character_profiles: Optional[Dict[str, Any]] = None,
    ) -> CheckResult:
        """执行角色偏离检查"""
        issues = []
        self.issue_counter = 0

        state = self.state_manager.load_state()

        # 构建角色档案
        profiles = self._build_character_profiles(state)
        if character_profiles:
            profiles.update(character_profiles)

        # 检查每个主要角色
        for char_name, profile in profiles.items():
            char_issues = await self._check_character_behavior(
                chapter_num, content, char_name, profile
            )
            issues.extend(char_issues)

        score = self._calculate_score(issues)
        summary = self._generate_summary(issues)

        return CheckResult(
            checker="ooc",
            score=score,
            issues=issues,
            summary=summary,
        )

    def _build_character_profiles(self, state) -> Dict[str, Any]:
        """从状态管理器构建角色档案"""
        profiles = {}
        for cs in state.character_states:
            profiles[cs.name] = {
                "gender": cs.gender,  # 【修复】添加性别
                "cultivation": cs.cultivation,
                "status": cs.status,
                "personality": cs.personality,  # 【修复】添加性格
                "traits": cs.traits,  # 【修复】添加特征
                "background": cs.background,  # 【修复】添加背景
                "relationships": cs.relationships,
                "key_items": cs.key_items,
                "knowledge": cs.knowledge,  # 【修复】添加知识
                "notes": cs.notes,
            }

        # 添加主角信息（合并 character_states 和 protagonist dict）
        protagonist = state.protagonist.get("name", "")
        if protagonist:
            if protagonist not in profiles:
                profiles[protagonist] = {}
            
            # 合并主角的完整信息
            profiles[protagonist].update({
                "is_protagonist": True,
                "desire": state.protagonist.get("desire", ""),
                "flaw": state.protagonist.get("flaw", ""),
                "golden_finger": state.protagonist.get("golden_finger", ""),
                "traits": state.protagonist.get("traits", []),
                "background": state.protagonist.get("background", ""),
            })
            
            # 【关键修复】确保主角性别被设置
            if not profiles[protagonist].get("gender"):
                profiles[protagonist]["gender"] = state.protagonist.get("gender", "男")

        return profiles

    async def _check_character_behavior(
        self,
        chapter_num: int,
        content: str,
        char_name: str,
        profile: Dict[str, Any],
    ) -> List[Issue]:
        """检查单个角色的行为一致性"""
        issues = []

        prompt = f"""
你是角色行为一致性检查员。请检查角色【{char_name}】在本章的行为是否符合其人设。

## 角色档案
- 性别: {profile.get('gender', '未知')}
- 修为/境界: {profile.get('cultivation', '未知')}
- 当前状态: {profile.get('status', '未知')}
- 性格: {profile.get('personality', profile.get('traits', '未知'))}
- 欲望/目标: {profile.get('desire', '未知')}
- 缺陷: {profile.get('flaw', '未知')}
- 金手指: {profile.get('golden_finger', '无')}
- 背景: {profile.get('background', '无')}
- 关系: {profile.get('relationships', {})}
- 知道的关键信息: {profile.get('knowledge', [])}
- 备注: {profile.get('notes', '无')}

## 章节内容（搜索该角色的所有行为描写）
{content[:5000]}

请检查：
1. 该角色的言行是否符合其性别和性格设定？
2. 该角色的决策是否与其目标一致？
3. 如果角色行为异常，是否有合理的解释？（如：受到外力影响、经历重大打击）
4. 是否有"人设崩塌"的情况？

输出 JSON 格式：
{{
  "level": "none|slight|moderate|severe",
  "issues": [
    {{
      "severity": "high|medium|low",
      "level": "slight|moderate|severe",
      "description": "问题描述",
      "location": "位置",
      "has_explanation": true/false,
      "suggestion": "修复建议"
    }}
  ]
}}
"""
        try:
            response = await self.llm.generate(
                prompt=prompt,
                system_prompt="你是角色行为一致性检查员，专门发现 OOC（Out of Character）行为。",
                temperature=0.2,
                max_tokens=1024,
            )

            import json
            json_match = re.search(r'\{.*\}', response.text, re.DOTALL)
            if json_match:
                result = json.loads(json_match.group())
                level = result.get("level", "none")

                for p in result.get("issues", []):
                    self.issue_counter += 1
                    issue_level = p.get("level", "moderate")
                    severity = p.get("severity", "medium")

                    # 根据严重程度调整 severity
                    if issue_level == "severe" and not p.get("has_explanation", False):
                        severity = "high"
                    elif issue_level == "moderate" and not p.get("has_explanation", False):
                        severity = "medium"
                    else:
                        severity = "low"

                    issues.append(Issue(
                        id=f"OOC-{self.issue_counter:03d}",
                        severity=severity,
                        category=f"ooc_{char_name}",
                        description=f"【{char_name}】{p.get('description', '')}",
                        location=p.get("location", ""),
                        suggestion=p.get("suggestion", ""),
                    ))
        except Exception as e:
            logger.warning(f"角色【{char_name}】行为检查失败: {e}")

        return issues

    def _calculate_score(self, issues: List[Issue]) -> int:
        """计算角色一致性得分"""
        score = 100
        for issue in issues:
            if issue.severity == "high":
                score -= 25
            elif issue.severity == "medium":
                score -= 15
            else:
                score -= 5
        return max(0, score)

    def _generate_summary(self, issues: List[Issue]) -> str:
        """生成检查总结"""
        if not issues:
            return "角色行为一致性检查通过，未发现 OOC 行为。"

        high = sum(1 for i in issues if i.severity == "high")
        medium = sum(1 for i in issues if i.severity == "medium")
        low = sum(1 for i in issues if i.severity == "low")

        summary = f"角色行为检查发现 {len(issues)} 个问题："
        if high > 0:
            summary += f"\n- 严重崩坏: {high} 个"
        if medium > 0:
            summary += f"\n- 中度扭曲: {medium} 个"
        if low > 0:
            summary += f"\n- 轻微偏离: {low} 个"

        return summary
