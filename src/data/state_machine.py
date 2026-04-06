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
    
    def _is_combat_action(self, state: EntityState) -> bool:
        """判断是否是战斗行为（需要AI辅助判断）"""
        # 这个需要结合AI对当前行为的语义理解
        # 这里返回True表示"可能是战斗"，实际由拦截器传入上下文
        return True
    
    def _is_heavy_skill_action(self, state: EntityState) -> bool:
        """判断是否是大招"""
        return True
    
    def _validate_realm_ability(self, state: EntityState) -> bool:
        """校验境界能力"""
        # 需要从配置文件读取境界等级顺序
        return True
    
    def _validate_item_usage(self, state: EntityState) -> bool:
        """校验物品使用"""
        return True
    
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
    
    def update_state_from_text(
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
        old_state = state.model_dump()
        
        # 这里使用AI提取状态变化
        if llm:
            changes = self._extract_state_changes_with_ai(state, text_content, llm)
            self._apply_changes(state, changes)
        
        state.last_updated_chapter = chapter_num
        state.last_updated = datetime.now().isoformat()
        
        # 保存
        self._save_state()
        return True
    
    def _extract_state_changes_with_ai(
        self, 
        state: EntityState, 
        text: str, 
        llm
    ) -> Dict[str, Any]:
        """用AI提取状态变化"""
        # 这里调用LLM提取状态变化
        pass
    
    def _apply_changes(self, state: EntityState, changes: Dict[str, Any]):
        """应用状态变化"""
        for key, value in changes.items():
            if hasattr(state, key):
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
