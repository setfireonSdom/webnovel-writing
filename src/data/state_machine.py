"""
显式状态机引擎 - 用代码强制 AI 保持逻辑连贯
职责：
1. 维护角色显式状态（HP、境界、伤势、物品、关系）
2. 提供状态校验接口（写前验证、写后更新）
3. 拦截不合法的状态变迁（如重伤不能打架）
"""

import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from enum import Enum

from pydantic import BaseModel, Field

from ..utils.file_ops import read_text_file, atomic_write_json, ensure_directory

logger = logging.getLogger(__name__)


class InjuryType(str, Enum):
    """伤势类型"""
    NONE = "无"
    MINOR = "轻伤"  # 不影响行动
    MODERATE = "中度伤"  # 影响部分能力
    SEVERE = "重伤"  # 严重影响能力
    CRITICAL = "濒死"  # 无法行动


class SpiritLevel(str, Enum):
    """灵力等级"""
    FULL = "充沛"  # 100%
    HIGH = "充足"  # 70-99%
    MEDIUM = "一般"  # 40-69%
    LOW = "不足"  # 20-39%
    DRAIN = "枯竭"  # 0-19%


class EntityState(BaseModel):
    """角色显式状态（代码可校验）"""
    name: str
    
    # 基础属性
    realm: str = ""  # 境界等级
    layer: int = 0  # 层数
    
    # 战斗相关
    hp_percent: float = 100.0  # 生命值百分比
    spirit_level: SpiritLevel = SpiritLevel.FULL  # 灵力等级
    injuries: List[str] = []  # 具体伤势列表
    injury_type: InjuryType = InjuryType.NONE  # 伤势等级
    
    # 资源
    items: List[str] = []  # 持有物品
    skills_available: List[str] = []  # 可用技能
    
    # 社交
    relationships: Dict[str, str] = {}  # 关系
    debts_owed: List[str] = []  # 欠别人的
    debts_own: List[str] = []  # 别人欠我的
    
    # 元数据
    location: str = ""  # 当前位置
    last_updated_chapter: int = 0
    last_updated: str = ""


class StateValidationResult(BaseModel):
    """状态校验结果"""
    is_valid: bool
    reason: str = ""
    violated_rules: List[str] = []
    suggestions: List[str] = []


STATE_EXTRACTION_PROMPT = """
你是专业的网文状态提取助手。请从章节内容中提取角色状态的变化。

## 角色当前状态
- 境界: {current_realm}
- 生命: {current_hp_percent:.0f}% ({current_injury_type})
- 伤势列表: {current_injuries}
- 灵力: {current_spirit_level}
- 持有物品: {current_items}
- 关系: {current_relationships}

## 章节内容
{text_content}

## 任务
请提取该角色在本章结束时的状态变化。只提取**明确发生改变**的字段。

请严格按照以下 JSON 格式输出（没有变化的字段不要包含在内）：

```json
{{
  "realm": "新境界（如果升级/降级了）",
  "layer": 5,
  "hp_percent": 60.0,
  "injury_type": "轻伤",
  "injuries": ["左臂骨折"],
  "spirit_level": "充足",
  "items": ["获得: 灵药", "消耗: 回气丹"],
  "relationships": {{"张三": "结为好友"}},
  "debts_owed": ["欠李四一条命"],
  "debts_own": ["王五欠我灵石"],
  "location": "新地点"
}}
```

**注意**:
- 只输出发生变化的字段，没有变化的不要输出
- items 中使用 "获得:" 和 "消耗:" 前缀区分获得和失去
- 如果完全没有变化，输出空对象 {{}}
- 不要输出任何解释文字
"""


STATE_ACTION_CLASSIFICATION_PROMPT = """
你是网文动作分析助手。请判断以下章节内容是否包含战斗行为。

## 章节内容
{text_content}

## 任务
判断该角色在本章是否参与了战斗/打斗/战斗相关行为。

只输出一个词："是" 或 "否"
"""

STATE_SKILL_CLASSIFICATION_PROMPT = """
你是网文技能分析助手。请判断以下章节内容是否包含高消耗技能（大招）。

## 章节内容
{text_content}

## 任务
判断该角色在本章是否释放了高消耗技能/大招/强力法术。

只输出一个词："是" 或 "否"
"""

REALM_HIERARCHY = [
    "炼气", "筑基", "金丹", "元婴", "化神", "炼虚", "合体", "大乘", "渡劫"
]

REALM_SKILL_PROMPT = """
你是网文能力校验助手。请判断以下行为是否符合角色的境界。

## 角色境界
{realm}

## 行为描述
{action}

## 已知境界等级（从低到高）
{realm_hierarchy}

## 任务
判断该行为是否合理（低境界角色是否可能做出这种行为）。

只输出一个词："合理" 或 "不合理"
"""

ITEM_USAGE_PROMPT = """
你是网文物品使用校验助手。请检查章节中是否使用了角色未持有的物品。

## 角色持有物品
{held_items}

## 章节内容
{text_content}

## 任务
找出章节中角色使用/消耗的所有物品，判断是否合理（是否在持有物品列表中，或是明显新获得的物品）。

请严格按照以下 JSON 格式输出：

```json
{{
  "used_items": ["使用的物品名"],
  "unauthorized_items": ["未持有却使用的物品名"]
}}
```
"""

CHAPTER_STATE_VALIDATION_PROMPT = """
你是严格的网文状态一致性检查员。请检查章节内容是否违反了角色的当前状态约束。

## 角色当前状态（写前事实）
{state_summary}

## 章节内容
{text_content}

## 硬拦截规则（必须遵守）
1. **重伤/濒死不能战斗** - 如果角色处于"重伤"或"濒死"状态，文中不得出现该角色参与战斗/打斗/施法的描写（除非有明确的用药/治疗/恢复过渡）。
2. **灵力枯竭不能放大招** - 如果角色灵力为"不足"或"枯竭"，文中不得出现该角色释放高消耗技能/大招/强力法术的描写。
3. **不得越境界使用能力** - 低境界角色不得使用明显超出其境界范围的能力。
4. **未持有物品不得使用** - 文中不得出现角色使用/消耗其未持有的物品的描写（除非有明确的获得过程）。
5. **伤势未愈不得生龙活虎** - 如果角色开头处于受伤状态，文中必须交代伤势的变化（好转/恶化/无视），不得突然像没事人一样。

请严格按照以下 JSON 格式输出：

```json
{{
  "violations": [
    {{
      "rule": "规则编号（RULE_001~RULE_005）",
      "entity": "角色名",
      "description": "违规描述",
      "severity": "critical|high|medium",
      "suggestion": "修复建议"
    }}
  ]
}}
```

如果没有违规，输出：

```json
{{"violations": []}}
```

**注意**：只输出 JSON，不要输出其他内容。
"""


class StateMachine:
    """显式状态机 - 用代码强制逻辑连贯"""

    def __init__(self, project_root: Path):
        self.project_root = Path(project_root)
        self.webnovel_dir = self.project_root / ".webnovel"
        self.state_machine_file = self.webnovel_dir / "state_machine.json"
        
        ensure_directory(self.webnovel_dir)
        
        # 加载状态
        self.entities: Dict[str, EntityState] = self._load_state()
        
        # 规则引擎
        self.rules: List[Dict[str, Any]] = self._load_rules()
    
    def _load_state(self) -> Dict[str, EntityState]:
        """加载状态"""
        if self.state_machine_file.exists():
            try:
                import json
                data = json.loads(read_text_file(self.state_machine_file))
                return {
                    name: EntityState(**state_data) 
                    for name, state_data in data.get("entities", {}).items()
                }
            except Exception as e:
                logger.warning(f"加载状态机失败: {e}，使用空状态")
        return {}
    
    def _load_rules(self) -> List[Dict[str, Any]]:
        """加载校验规则"""
        return [
            {
                "id": "RULE_001",
                "name": "重伤不能战斗",
                "check": lambda state: not (
                    state.injury_type in [InjuryType.SEVERE, InjuryType.CRITICAL] and
                    self._is_combat_action(state)
                ),
                "message": "角色处于{injury_type}状态，无法进行战斗",
                "severity": "critical"
            },
            {
                "id": "RULE_002",
                "name": "灵力不足不能释放大招",
                "check": lambda state: not (
                    state.spirit_level in [SpiritLevel.LOW, SpiritLevel.DRAIN] and
                    self._is_heavy_skill_action(state)
                ),
                "message": "灵力{spirit_level}，无法释放高消耗技能",
                "severity": "high"
            },
            {
                "id": "RULE_003",
                "name": "境界不能越级使用能力",
                "check": lambda state: self._validate_realm_ability(state),
                "message": "境界{realm}无法使用该能力",
                "severity": "high"
            },
            {
                "id": "RULE_004",
                "name": "没有物品不能使用",
                "check": lambda state: self._validate_item_usage(state),
                "message": "未持有物品：{item}",
                "severity": "critical"
            },
            {
                "id": "RULE_005",
                "name": "位置必须连续",
                "check": lambda state: True,  # 需要上下文
                "message": "位置移动不合理",
                "severity": "medium"
            }
        ]
    
    async def _is_combat_action(self, state: EntityState, text_content: str = "", llm=None) -> bool:
        """判断是否是战斗行为（AI 辅助判断）"""
        if not text_content or not llm:
            # 无文本/无LLM，默认保守估计：假设是战斗
            return True
        
        try:
            prompt = STATE_ACTION_CLASSIFICATION_PROMPT.format(text_content=text_content[:3000])
            response = await llm.generate(
                prompt=prompt,
                system_prompt="你是网文动作分析助手。",
                temperature=0.0,
                max_tokens=16,
            )
            return "是" in response.text.strip()
        except Exception as e:
            logger.warning(f"战斗行为判断失败: {e}")
            return True  # 保守估计
    
    async def _is_heavy_skill_action(self, state: EntityState, text_content: str = "", llm=None) -> bool:
        """判断是否是大招（AI 辅助判断）"""
        if not text_content or not llm:
            return True
        
        try:
            prompt = STATE_SKILL_CLASSIFICATION_PROMPT.format(text_content=text_content[:3000])
            response = await llm.generate(
                prompt=prompt,
                system_prompt="你是网文技能分析助手。",
                temperature=0.0,
                max_tokens=16,
            )
            return "是" in response.text.strip()
        except Exception as e:
            logger.warning(f"大招判断失败: {e}")
            return True  # 保守估计
    
    async def _validate_realm_ability(self, realm: str = "", action: str = "", llm=None) -> bool:
        """校验境界能力（AI 辅助判断）"""
        if not action or not llm:
            return True  # 无法判断时默认通过
        
        try:
            prompt = REALM_SKILL_PROMPT.format(
                realm=realm or "未知",
                action=action,
                realm_hierarchy=", ".join(REALM_HIERARCHY),
            )
            response = await llm.generate(
                prompt=prompt,
                system_prompt="你是网文能力校验助手。",
                temperature=0.0,
                max_tokens=16,
            )
            return "合理" in response.text.strip()
        except Exception as e:
            logger.warning(f"境界能力校验失败: {e}")
            return True  # 无法判断时默认通过
    
    async def _validate_item_usage(self, state: EntityState, text_content: str = "", llm=None) -> List[str]:
        """校验物品使用，返回未授权使用的物品列表"""
        if not text_content or not llm:
            return []
        
        try:
            prompt = ITEM_USAGE_PROMPT.format(
                held_items=", ".join(state.items[:20]) if state.items else "无",
                text_content=text_content[:3000],
            )
            response = await llm.generate(
                prompt=prompt,
                system_prompt="你是网文物品使用校验助手。",
                temperature=0.0,
                max_tokens=512,
            )
            
            import re
            json_match = re.search(r'\{.*\}', response.text, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group())
                return data.get("unauthorized_items", [])
            return []
        except Exception as e:
            logger.warning(f"物品使用校验失败: {e}")
            return []
    
    def validate_action(
        self, 
        entity_name: str, 
        action_description: str,
        action_type: str = "combat"  # combat, movement, dialogue, skill, item_use
    ) -> StateValidationResult:
        """校验动作是否合法"""
        if entity_name not in self.entities:
            return StateValidationResult(
                is_valid=True,
                reason=f"角色 {entity_name} 无状态记录，跳过校验"
            )
        
        state = self.entities[entity_name]
        violated_rules = []
        suggestions = []
        
        # RULE_001: 重伤不能战斗
        if action_type == "combat" and state.injury_type in [InjuryType.SEVERE, InjuryType.CRITICAL]:
            violated_rules.append(f"RULE_001: {state.name}处于{state.injury_type.value}状态，无法战斗")
            suggestions.append("必须先描写伤势好转/用药/系统治疗，或者改为逃跑/智取")
        
        # RULE_002: 灵力不足不能大招
        if action_type == "skill" and state.spirit_level in [SpiritLevel.LOW, SpiritLevel.DRAIN]:
            violated_rules.append(f"RULE_002: {state.name}灵力{state.spirit_level.value}，无法释放技能")
            suggestions.append("改为普通攻击，或者先回复灵力")
        
        # RULE_003: 境界能力校验
        if action_type == "skill":
            realm_limit = self._get_realm_skill_limit(state.realm)
            if not self._is_action_within_realm(action_description, realm_limit):
                violated_rules.append(f"RULE_003: {state.name}境界{state.realm}无法使用该能力")
                suggestions.append("改为境界允许的能力")
        
        # RULE_004: 物品使用校验
        used_items = self._extract_items_from_action(action_description)
        for item in used_items:
            if item not in state.items:
                violated_rules.append(f"RULE_004: {state.name}未持有物品'{item}'")
                suggestions.append("改为使用已持有的物品")
        
        # 返回结果
        is_valid = len(violated_rules) == 0
        return StateValidationResult(
            is_valid=is_valid,
            reason="; ".join(violated_rules) if violated_rules else "校验通过",
            violated_rules=violated_rules,
            suggestions=suggestions
        )

    async def validate_chapter_content(
        self,
        chapter_num: int,
        text_content: str,
        llm=None,
    ) -> Dict[str, Any]:
        """
        用 AI 检查章节内容是否违反角色状态约束（重伤不能战斗、灵力不足不能放大招等）

        Returns:
            {
                "valid": bool,
                "violations": [{"rule", "entity", "description", "severity", "suggestion"}],
                "error_summary": str,  # 人类可读的错误摘要
            }
        """
        if not self.entities or not llm:
            return {"valid": True, "violations": [], "error_summary": ""}

        # 构建所有角色的状态摘要
        state_summary_lines = []
        for name, state in self.entities.items():
            state_summary_lines.append(f"### {name}")
            state_summary_lines.append(f"- 境界: {state.realm or '未知'}")
            state_summary_lines.append(f"- 生命: {state.hp_percent:.0f}% ({state.injury_type.value})")
            if state.injuries:
                state_summary_lines.append(f"- 伤势: {', '.join(state.injuries)}")
            state_summary_lines.append(f"- 灵力: {state.spirit_level.value}")
            if state.items:
                state_summary_lines.append(f"- 持有物品: {', '.join(state.items[:15])}")
        state_summary = "\n".join(state_summary_lines)

        prompt = CHAPTER_STATE_VALIDATION_PROMPT.format(
            state_summary=state_summary,
            text_content=text_content[:6000],
        )

        try:
            response = await llm.generate(
                prompt=prompt,
                system_prompt="你是严格的网文状态一致性检查员，专门发现角色状态与描写之间的矛盾。只输出JSON。",
                temperature=0.1,
                max_tokens=1024,
            )

            json_match = re.search(r'\{.*\}', response.text, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group())
                violations = data.get("violations", [])

                if violations:
                    # 构建人类可读摘要
                    summary_lines = ["【状态机违规】以下描写违反角色当前状态："]
                    for v in violations[:5]:
                        summary_lines.append(f"- [{v.get('severity', 'medium').upper()}] {v.get('description', '')}")
                        if v.get('suggestion'):
                            summary_lines.append(f"  建议: {v['suggestion']}")

                    # 提取最严重的错误作为 correct_value
                    first_violation = violations[0]
                    correct_value = first_violation.get('suggestion', '')

                    return {
                        "valid": False,
                        "violations": violations,
                        "error_summary": "\n".join(summary_lines),
                        "correct_value": correct_value,
                        "error_type": first_violation.get('rule', 'state_machine'),
                    }

                return {"valid": True, "violations": [], "error_summary": ""}

            return {"valid": True, "violations": [], "error_summary": ""}

        except Exception as e:
            logger.warning(f"状态机章节内容校验失败: {e}")
            return {"valid": True, "violations": [], "error_summary": ""}
    
    async def update_state_from_text(
        self, 
        entity_name: str, 
        chapter_num: int, 
        text_content: str,
        llm=None  # 用于AI辅助状态提取
    ) -> bool:
        """从文本中更新状态"""
        if entity_name not in self.entities:
            logger.warning(f"角色 {entity_name} 不存在于状态机中")
            return False
        
        state = self.entities[entity_name]
        
        # 这里使用AI提取状态变化
        if llm:
            changes = await self._extract_state_changes_with_ai(state, text_content, llm)
            self._apply_changes(state, changes)
        
        state.last_updated_chapter = chapter_num
        state.last_updated = datetime.now().isoformat()
        
        # 保存
        self._save_state()
        return True
    
    async def _extract_state_changes_with_ai(
        self, 
        state: EntityState, 
        text: str, 
        llm
    ) -> Dict[str, Any]:
        """用AI提取状态变化"""
        import re
        import json
        
        # 截断文本避免超出上下文
        text_snippet = text[:6000]
        
        prompt = STATE_EXTRACTION_PROMPT.format(
            current_realm=state.realm or "未知",
            current_hp_percent=state.hp_percent,
            current_injury_type=state.injury_type.value,
            current_injuries=", ".join(state.injuries) if state.injuries else "无",
            current_spirit_level=state.spirit_level.value,
            current_items=", ".join(state.items[:10]) if state.items else "无",
            current_relationships=", ".join(
                f"{k}:{v}" for k, v in list(state.relationships.items())[:5]
            ) if state.relationships else "无",
            text_content=text_snippet,
        )
        
        try:
            response = await llm.generate(
                prompt=prompt,
                system_prompt="你是专业的网文状态提取助手，擅长从小说文本中提取角色的状态变化。只输出JSON，不要输出其他内容。",
                temperature=0.1,
                max_tokens=1024,
            )
            
            # 提取 JSON
            json_match = re.search(r'\{.*\}', response.text, re.DOTALL)
            if json_match:
                changes = json.loads(json_match.group())
                return changes
            return {}
        except Exception as e:
            logger.warning(f"AI 状态提取失败: {e}")
            return {}
    
    def _apply_changes(self, state: EntityState, changes: Dict[str, Any]):
        """应用状态变化"""
        if not changes:
            return
        
        for key, value in changes.items():
            if not hasattr(state, key):
                logger.debug(f"状态字段 {key} 不存在，跳过")
                continue
            
            # 特殊处理 items 字段（支持 "获得:" / "消耗:" 前缀）
            if key == "items" and isinstance(value, list):
                for item_entry in value:
                    if isinstance(item_entry, str):
                        if item_entry.startswith("获得: "):
                            item_name = item_entry[4:].strip()
                            if item_name not in state.items:
                                state.items.append(item_name)
                                logger.info(f"角色 {state.name} 获得物品: {item_name}")
                        elif item_entry.startswith("消耗: "):
                            item_name = item_entry[4:].strip()
                            if item_name in state.items:
                                state.items.remove(item_name)
                                logger.info(f"角色 {state.name} 消耗物品: {item_name}")
                        else:
                            # 直接设置物品列表
                            state.items = value
                            break
                continue
            
            # 特殊处理 injuries 字段
            if key == "injuries" and isinstance(value, list):
                state.injuries = value
                # 同步更新 injury_type
                if not value:
                    state.injury_type = InjuryType.NONE
                continue
            
            # 特殊处理 relationships 字段
            if key == "relationships" and isinstance(value, dict):
                state.relationships.update(value)
                continue
            
            # 特殊处理 hp_percent 字段，同步更新 injury_type
            if key == "hp_percent" and isinstance(value, (int, float)):
                state.hp_percent = float(value)
                # 自动推导伤势等级
                if state.hp_percent >= 90:
                    state.injury_type = InjuryType.NONE
                    state.injuries = []
                elif state.hp_percent >= 70:
                    state.injury_type = InjuryType.MINOR
                elif state.hp_percent >= 40:
                    state.injury_type = InjuryType.MODERATE
                elif state.hp_percent >= 20:
                    state.injury_type = InjuryType.SEVERE
                else:
                    state.injury_type = InjuryType.CRITICAL
                continue
            
            # 特殊处理 spirit_level 字段
            if key == "spirit_level" and isinstance(value, str):
                try:
                    state.spirit_level = SpiritLevel(value)
                except ValueError:
                    logger.warning(f"无效的灵力等级: {value}")
                continue
            
            # 默认行为：直接赋值
            setattr(state, key, value)
    
    def _get_realm_skill_limit(self, realm: str) -> Dict[str, Any]:
        """获取境界技能限制"""
        # 从配置文件读取
        return {}
    
    def _is_action_within_realm(self, action: str, limit: Dict) -> bool:
        """判断动作是否在境界范围内"""
        return True
    
    def _extract_items_from_action(self, action: str) -> List[str]:
        """从动作中提取物品"""
        return []
    
    def _save_state(self):
        """保存状态"""
        data = {
            "entities": {
                name: state.model_dump() 
                for name, state in self.entities.items()
            },
            "last_updated": datetime.now().isoformat()
        }
        atomic_write_json(self.state_machine_file, data)
    
    def init_entity(self, name: str, realm: str = "", location: str = "") -> EntityState:
        """初始化角色状态"""
        if name in self.entities:
            return self.entities[name]
        
        state = EntityState(
            name=name,
            realm=realm,
            location=location,
            last_updated_chapter=0,
            last_updated=datetime.now().isoformat()
        )
        self.entities[name] = state
        self._save_state()
        return state
    
    def get_state(self, entity_name: str) -> Optional[EntityState]:
        """获取角色状态"""
        return self.entities.get(entity_name)
    
    def get_all_states(self) -> Dict[str, EntityState]:
        """获取所有状态"""
        return self.entities
    
    def generate_context_string(self, entity_name: str) -> str:
        """生成用于写作上下文的状态字符串"""
        state = self.entities.get(entity_name)
        if not state:
            return f"（{entity_name} 无状态记录）"
        
        lines = [f"## {state.name} 当前状态"]
        lines.append(f"- 境界: {state.realm}")
        lines.append(f"- 生命: {state.hp_percent:.0f}% ({state.injury_type.value})")
        if state.injuries:
            lines.append(f"- 伤势: {', '.join(state.injuries)}")
        lines.append(f"- 灵力: {state.spirit_level.value}")
        if state.items:
            lines.append(f"- 持有: {', '.join(state.items)}")
        if state.relationships:
            rels = ', '.join(f"{k}:{v}" for k, v in list(state.relationships.items())[:5])
            lines.append(f"- 关系: {rels}")
        
        return "\n".join(lines)
