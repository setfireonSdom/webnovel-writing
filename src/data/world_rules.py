"""
世界观规则库 - 自动提取、维护和检查
职责：
1. 从设定文件和章节中自动提取世界观规则
2. 维护规则变更历史
3. 在写作和审查时自动检查世界观一致性
"""

import json
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from ..utils.file_ops import read_text_file, write_text_file, atomic_write_json, ensure_directory
from ..llm.base import BaseLLM

logger = logging.getLogger(__name__)


class WorldRule(BaseModel):
    """单条世界观规则"""
    id: str  # 规则ID，如 "WR-001"
    category: str  # 类别：power_system, geography, faction, history, item, rule, custom
    name: str  # 规则名称
    content: str  # 规则内容（详细描述）
    constraints: Dict[str, Any] = Field(default_factory=dict)  # 约束条件
    source: str = "manual"  # 来源：manual(手动), auto_extract(自动提取), ai_generated(AI生成)
    priority: str = "high"  # high, medium, low
    created_chapter: int = 0
    last_verified_chapter: int = 0
    is_active: bool = True
    notes: str = ""


class WorldRulesState(BaseModel):
    """世界观规则状态"""
    version: str = "1.0.0"
    last_updated: str = ""
    rules: List[WorldRule] = Field(default_factory=list)
    change_log: List[Dict[str, Any]] = Field(default_factory=list)  # 变更记录
    statistics: Dict[str, Any] = Field(default_factory=dict)  # 统计信息


class WorldRulesManager:
    """世界观规则管理器"""

    def __init__(self, project_root: Path):
        self.project_root = Path(project_root)
        self.webnovel_dir = self.project_root / ".webnovel"
        self.rules_file = self.webnovel_dir / "world_rules.json"
        self.setting_dir = self.project_root / "设定集"
        
        ensure_directory(self.webnovel_dir)
        
        # 加载或初始化规则
        self.state = self._load_or_init_rules()

    def _load_or_init_rules(self) -> WorldRulesState:
        """加载规则或初始化"""
        if self.rules_file.exists():
            try:
                data = json.loads(read_text_file(self.rules_file))
                return WorldRulesState(**data)
            except Exception as e:
                logger.warning(f"加载世界观规则失败: {e}，使用默认规则")
                return self._create_default_rules()
        else:
            return self._create_default_rules()

    def _create_default_rules(self) -> WorldRulesState:
        """创建默认规则（从设定文件提取）"""
        state = WorldRulesState(
            last_updated=datetime.now().isoformat(),
            rules=[],
            statistics={"total_rules": 0, "active_rules": 0, "last_auto_extract_chapter": 0}
        )
        
        # 尝试从设定文件提取规则
        self._extract_rules_from_settings(state)
        
        # 保存
        self._save_rules(state)
        
        return state

    def _extract_rules_from_settings(self, state: WorldRulesState):
        """从设定文件提取规则"""
        rule_counter = 0
        
        # 从力量体系提取
        power_file = self.setting_dir / "力量体系.md"
        if power_file.exists():
            content = read_text_file(power_file)
            rule_counter = self._parse_power_system(content, state, rule_counter)
        
        # 从世界观提取
        worldview_file = self.setting_dir / "世界观.md"
        if worldview_file.exists():
            content = read_text_file(worldview_file)
            rule_counter = self._parse_worldview(content, state, rule_counter)
        
        # 从角色设定提取
        character_file = self.setting_dir / "角色设定.md"
        if character_file.exists():
            content = read_text_file(character_file)
            rule_counter = self._parse_characters(content, state, rule_counter)
        
        state.statistics["total_rules"] = len(state.rules)
        state.statistics["active_rules"] = sum(1 for r in state.rules if r.is_active)

    def _parse_power_system(self, content: str, state: WorldRulesState, counter: int) -> int:
        """从力量体系文件解析规则"""
        # 简单解析：按段落提取
        lines = content.strip().split("\n")
        current_section = ""
        
        for line in lines:
            line = line.strip()
            if line.startswith("## "):
                current_section = line[3:].strip()
            elif line and current_section:
                counter += 1
                rule = WorldRule(
                    id=f"WR-{counter:03d}",
                    category="power_system",
                    name=f"{current_section}规则",
                    content=line[:200],
                    source="auto_extract",
                    priority="high",
                    created_chapter=0
                )
                state.rules.append(rule)
        
        return counter

    def _parse_worldview(self, content: str, state: WorldRulesState, counter: int) -> int:
        """从世界观文件解析规则"""
        lines = content.strip().split("\n")
        current_section = ""
        
        for line in lines:
            line = line.strip()
            if line.startswith("## "):
                current_section = line[3:].strip()
            elif line and current_section:
                counter += 1
                rule = WorldRule(
                    id=f"WR-{counter:03d}",
                    category="worldview",
                    name=f"{current_section}",
                    content=line[:200],
                    source="auto_extract",
                    priority="medium",
                    created_chapter=0
                )
                state.rules.append(rule)
        
        return counter

    def _parse_characters(self, content: str, state: WorldRulesState, counter: int) -> int:
        """从角色设定文件解析规则"""
        # 提取主角核心设定
        protagonist_match = re.search(r'## 主角\n(.*?)(?=##|$)', content, re.DOTALL)
        if protagonist_match:
            counter += 1
            rule = WorldRule(
                id=f"WR-{counter:03d}",
                category="character",
                name="主角核心设定",
                content=protagonist_match.group(1).strip()[:300],
                source="auto_extract",
                priority="high",
                created_chapter=0
            )
            state.rules.append(rule)
        
        return counter

    def add_rule(self, rule: WorldRule) -> str:
        """添加规则"""
        if not rule.id:
            # 自动生成ID
            max_id = max([0] + [int(r.id.split("-")[1]) for r in self.state.rules if r.id.startswith("WR-")])
            rule.id = f"WR-{max_id + 1:03d}"
        
        self.state.rules.append(rule)
        self._log_change("add", rule.id, f"添加规则: {rule.name}")
        self._save_rules(self.state)
        return rule.id

    def update_rule(self, rule_id: str, **kwargs) -> bool:
        """更新规则"""
        for i, rule in enumerate(self.state.rules):
            if rule.id == rule_id:
                old_rule = rule.model_dump()
                for key, value in kwargs.items():
                    if hasattr(rule, key):
                        setattr(rule, key, value)
                
                self._log_change("update", rule_id, f"更新规则: {rule.name}")
                self._save_rules(self.state)
                return True
        return False

    def deactivate_rule(self, rule_id: str, reason: str = "") -> bool:
        """停用规则（而非删除）"""
        for rule in self.state.rules:
            if rule.id == rule_id:
                rule.is_active = False
                rule.notes = f"已停用: {reason}"
                self._log_change("deactivate", rule_id, f"停用规则: {rule.name}")
                self._save_rules(self.state)
                return True
        return False

    def get_active_rules(self, category: Optional[str] = None) -> List[WorldRule]:
        """获取活跃规则"""
        rules = [r for r in self.state.rules if r.is_active]
        if category:
            rules = [r for r in rules if r.category == category]
        return rules

    def get_all_rules(self) -> List[WorldRule]:
        """获取所有规则"""
        return self.state.rules

    def get_rules_for_context(self) -> str:
        """生成用于写作上下文的规则文本"""
        active_rules = self.get_active_rules()
        if not active_rules:
            return "（暂无世界观规则）"
        
        # 按类别分组
        by_category = {}
        for rule in active_rules:
            by_category.setdefault(rule.category, []).append(rule)
        
        lines = ["## 世界观规则（必须遵守）"]
        for category, rules in by_category.items():
            lines.append(f"\n### {self._category_name(category)}")
            for rule in rules:
                lines.append(f"- [{rule.id}] {rule.content}")
        
        return "\n".join(lines)

    def _category_name(self, category: str) -> str:
        """类别中文名"""
        names = {
            "power_system": "力量体系",
            "geography": "地理环境",
            "faction": "势力组织",
            "history": "历史事件",
            "item": "物品道具",
            "rule": "世界规则",
            "character": "角色设定",
            "worldview": "世界观",
            "custom": "自定义"
        }
        return names.get(category, category)

    def _log_change(self, action: str, rule_id: str, description: str):
        """记录变更"""
        self.state.change_log.append({
            "action": action,
            "rule_id": rule_id,
            "description": description,
            "timestamp": datetime.now().isoformat(),
            "chapter": self.state.statistics.get("last_auto_extract_chapter", 0)
        })

    def _save_rules(self, state: WorldRulesState):
        """保存规则"""
        state.last_updated = datetime.now().isoformat()
        state.statistics["total_rules"] = len(state.rules)
        state.statistics["active_rules"] = sum(1 for r in state.rules if r.is_active)
        atomic_write_json(self.rules_file, state.model_dump())

    async def auto_extract_rules(self, llm: BaseLLM, chapter_num: int, chapter_content: str):
        """AI自动从章节中提取世界观规则"""
        # 获取现有规则作为参考
        existing_rules_text = self.get_rules_for_context()
        
        prompt = f"""
你是世界观规则提取专家。请从章节内容中提取或更新世界观规则。

## 现有规则（供参考，避免矛盾）
{existing_rules_text}

## 章节内容
{chapter_content[:5000]}

## 任务
1. 提取新的世界观规则（力量体系、地理、势力、物品、历史等）
2. 检查是否与现有规则矛盾
3. 如发现矛盾，标记需要更新

请严格按JSON格式输出（如无新规则输出空列表）：
```json
{{
  "new_rules": [
    {{
      "category": "power_system|geography|faction|history|item|rule|custom",
      "name": "规则名称",
      "content": "规则详细描述",
      "priority": "high|medium|low"
    }}
  ],
  "conflicts": [
    {{
      "rule_id": "WR-XXX",
      "conflict_description": "矛盾描述",
      "suggestion": "建议如何处理"
    }}
  ]
}}
```
"""
        try:
            response = await llm.generate(
                prompt=prompt,
                system_prompt="你是世界观规则提取专家，擅长从文本中抽象出世界观规则。",
                temperature=0.3,
                max_tokens=2048,
            )
            
            # 解析响应
            json_match = re.search(r'\{.*\}', response.text, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group())
                
                # 添加新规则
                for new_rule_data in data.get("new_rules", []):
                    rule = WorldRule(
                        category=new_rule_data.get("category", "custom"),
                        name=new_rule_data.get("name", ""),
                        content=new_rule_data.get("content", ""),
                        source="ai_generated",
                        priority=new_rule_data.get("priority", "medium"),
                        created_chapter=chapter_num,
                        last_verified_chapter=chapter_num
                    )
                    self.add_rule(rule)
                    logger.info(f"自动提取规则: {rule.name}")
                
                # 标记冲突的规则
                for conflict in data.get("conflicts", []):
                    rule_id = conflict.get("rule_id")
                    if rule_id:
                        self.update_rule(
                            rule_id,
                            notes=f"冲突: {conflict.get('conflict_description')}. {conflict.get('suggestion', '')}"
                        )
                        logger.warning(f"规则冲突: {conflict.get('conflict_description')}")
                
                # 更新统计
                self.state.statistics["last_auto_extract_chapter"] = chapter_num
                self._save_rules(self.state)
                
                return {
                    "new_rules_count": len(data.get("new_rules", [])),
                    "conflicts_count": len(data.get("conflicts", []))
                }
        
        except Exception as e:
            logger.error(f"自动提取规则失败: {e}")
        
        return {"new_rules_count": 0, "conflicts_count": 0}

    def generate_audit_report(self) -> str:
        """生成审计报告"""
        lines = ["# 世界观规则审计报告\n"]
        lines.append(f"生成时间: {datetime.now().isoformat()}\n")
        
        # 统计
        total = len(self.state.rules)
        active = sum(1 for r in self.state.rules if r.is_active)
        inactive = total - active
        by_category = {}
        for rule in self.state.rules:
            by_category.setdefault(rule.category, 0)
            by_category[rule.category] += 1
        
        lines.append(f"## 统计信息")
        lines.append(f"- 总规则数: {total}")
        lines.append(f"- 活跃规则: {active}")
        lines.append(f"- 停用规则: {inactive}")
        lines.append(f"- 按类别: {', '.join(f'{k}: {v}' for k, v in by_category.items())}")
        lines.append("")
        
        # 最近变更
        if self.state.change_log:
            lines.append(f"## 最近变更（最近10条）")
            for change in self.state.change_log[-10:]:
                lines.append(f"- [{change['timestamp']}] {change['description']}")
            lines.append("")
        
        # 潜在问题
        lines.append(f"## 潜在问题检查")
        
        issues = []
        # 检查重复规则
        names = [r.name for r in self.state.rules if r.is_active]
        duplicates = set([n for n in names if names.count(n) > 1])
        if duplicates:
            issues.append(f"发现重复规则名称: {', '.join(duplicates)}")
        
        # 检查长期未验证的规则
        old_rules = [r for r in self.state.rules if r.is_active and r.last_verified_chapter > 0]
        if old_rules:
            max_chapter = max(r.last_verified_chapter for r in self.state.rules)
            unverified = [r for r in old_rules if max_chapter - r.last_verified_chapter > 100]
            if unverified:
                issues.append(f"发现 {len(unverified)} 条规则超过100章未验证")
        
        if issues:
            for issue in issues:
                lines.append(f"⚠️ {issue}")
        else:
            lines.append("✅ 未发现明显问题")
        
        lines.append("")
        return "\n".join(lines)
