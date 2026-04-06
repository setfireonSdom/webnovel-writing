"""
角色弧光追踪系统 - 自动追踪角色成长、心理变化、关系演变
职责：
1. 记录角色成长阶段和心理状态
2. 追踪角色关系演变历史
3. 防止"境界倒退"、"性格突变"、"关系跳跃"
4. 生成角色弧光报告
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from ..utils.file_ops import read_text_file, write_text_file, atomic_write_json, ensure_directory

logger = logging.getLogger(__name__)


class CharacterArcSnapshot(BaseModel):
    """角色弧光快照（某个时间点的状态）"""
    chapter: int
    timestamp: str
    
    # 外在状态
    cultivation: str = ""  # 修为境界
    skills: List[str] = Field(default_factory=list)  # 技能
    items: List[str] = Field(default_factory=list)  # 物品
    status: str = "active"  # 身体状态：active, injured, poisoned, etc.
    
    # 内在状态
    motivation: str = ""  # 当前动机
    emotional_state: str = "stable"  # 情绪状态：stable, anxious, angry, confident, etc.
    moral_alignment: str = ""  # 道德倾向（如果发生变化）
    
    # 关系
    relationships: Dict[str, str] = Field(default_factory=dict)  # 角色名 -> 关系描述
    
    # 重要事件
    key_events: List[str] = Field(default_factory=list)  # 本章发生的重要事
    
    # 成长指标
    growth_markers: List[str] = Field(default_factory=list)  # 成长标志


class CharacterArc(BaseModel):
    """单个角色的完整弧光"""
    name: str
    role: str = "protagonist"  # protagonist, supporting, antagonist
    arc_type: str = ""  # 弧光类型：growth, fall, redemption, corruption, etc.
    
    # 初始设定
    initial_desire: str = ""  # 初始欲望
    initial_flaw: str = ""  # 初始缺陷
    initial_state: CharacterArcSnapshot = None
    
    # 弧光轨迹
    snapshots: List[CharacterArcSnapshot] = Field(default_factory=list)
    
    # 关键转折点
    turning_points: List[Dict[str, Any]] = Field(default_factory=list)
    # {chapter, description, type, impact}
    
    # 关系演变历史
    relationship_history: List[Dict[str, Any]] = Field(default_factory=list)
    # {chapter, character, old_relation, new_relation, trigger_event}
    
    # 能力变化历史
    power_progression: List[Dict[str, Any]] = Field(default_factory=list)
    # {chapter, old_level, new_level, breakthrough_event}
    
    # 状态标记
    is_consistent: bool = True
    consistency_issues: List[str] = Field(default_factory=list)
    
    # 最后更新
    last_updated_chapter: int = 0
    last_updated: str = ""


class CharacterArcTracker:
    """角色弧光追踪器"""

    def __init__(self, project_root: Path):
        self.project_root = Path(project_root)
        self.webnovel_dir = self.project_root / ".webnovel"
        self.tracker_file = self.webnovel_dir / "character_arcs.json"
        
        ensure_directory(self.webnovel_dir)
        
        # 加载或初始化
        self.arcs: Dict[str, CharacterArc] = self._load_or_init_arcs()

    def _load_or_init_arcs(self) -> Dict[str, CharacterArc]:
        """加载弧光或初始化"""
        if self.tracker_file.exists():
            try:
                data = json.loads(read_text_file(self.tracker_file))
                return {name: CharacterArc(**arc_data) for name, arc_data in data.items()}
            except Exception as e:
                logger.warning(f"加载角色弧光失败: {e}")
                return {}
        return {}

    def _save_arcs(self):
        """保存弧光"""
        data = {name: arc.model_dump() for name, arc in self.arcs.items()}
        atomic_write_json(self.tracker_file, data)

    def init_character(self, name: str, role: str, desire: str, flaw: str, 
                      cultivation: str = "", initial_state: Optional[Dict] = None) -> CharacterArc:
        """初始化角色弧光"""
        if name in self.arcs:
            return self.arcs[name]
        
        snapshot = CharacterArcSnapshot(
            chapter=0,
            timestamp=datetime.now().isoformat(),
            cultivation=cultivation,
            motivation=desire,
            emotional_state="stable",
            relationships=initial_state.get("relationships", {}) if initial_state else {},
            growth_markers=initial_state.get("growth_markers", []) if initial_state else []
        )
        
        arc = CharacterArc(
            name=name,
            role=role,
            initial_desire=desire,
            initial_flaw=flaw,
            initial_state=snapshot,
            last_updated_chapter=0,
            last_updated=datetime.now().isoformat()
        )
        
        self.arcs[name] = arc
        self._save_arcs()
        return arc

    def update_snapshot(self, name: str, chapter: int, 
                       new_state: Dict[str, Any]) -> bool:
        """更新角色快照"""
        if name not in self.arcs:
            logger.warning(f"角色 {name} 未初始化弧光")
            return False
        
        arc = self.arcs[name]
        
        snapshot = CharacterArcSnapshot(
            chapter=chapter,
            timestamp=datetime.now().isoformat(),
            cultivation=new_state.get("cultivation", ""),
            skills=new_state.get("skills", []),
            items=new_state.get("items", []),
            status=new_state.get("status", "active"),
            motivation=new_state.get("motivation", ""),
            emotional_state=new_state.get("emotional_state", "stable"),
            moral_alignment=new_state.get("moral_alignment", ""),
            relationships=new_state.get("relationships", {}),
            key_events=new_state.get("key_events", []),
            growth_markers=new_state.get("growth_markers", [])
        )
        
        arc.snapshots.append(snapshot)
        arc.last_updated_chapter = chapter
        arc.last_updated = datetime.now().isoformat()
        
        # 检查转折点
        self._detect_turning_points(arc, chapter, new_state)
        
        # 检查关系变化
        self._detect_relationship_changes(arc, chapter, new_state)
        
        # 检查能力变化
        self._detect_power_changes(arc, chapter, new_state)
        
        # 检查一致性
        self._check_consistency(arc, chapter, new_state)
        
        self._save_arcs()
        return True

    def _detect_turning_points(self, arc: CharacterArc, chapter: int, 
                               new_state: Dict[str, Any]):
        """检测转折点"""
        # 检查是否有重大事件
        key_events = new_state.get("key_events", [])
        if key_events:
            arc.turning_points.append({
                "chapter": chapter,
                "description": "; ".join(key_events),
                "type": "event",
                "impact": "unknown",
                "timestamp": datetime.now().isoformat()
            })

    def _detect_relationship_changes(self, arc: CharacterArc, chapter: int,
                                     new_state: Dict[str, Any]):
        """检测关系变化"""
        if not arc.snapshots:
            return
        
        last_snapshot = arc.snapshots[-1]
        new_relationships = new_state.get("relationships", {})
        
        for char_name, relation in new_relationships.items():
            old_relation = last_snapshot.relationships.get(char_name, "")
            if old_relation and old_relation != relation:
                arc.relationship_history.append({
                    "chapter": chapter,
                    "character": char_name,
                    "old_relation": old_relation,
                    "new_relation": relation,
                    "timestamp": datetime.now().isoformat()
                })

    def _detect_power_changes(self, arc: CharacterArc, chapter: int,
                             new_state: Dict[str, Any]):
        """检测能力变化"""
        if not arc.snapshots:
            return
        
        last_snapshot = arc.snapshots[-1]
        new_cultivation = new_state.get("cultivation", "")
        
        if last_snapshot.cultivation and new_cultivation != last_snapshot.cultivation:
            arc.power_progression.append({
                "chapter": chapter,
                "old_level": last_snapshot.cultivation,
                "new_level": new_cultivation,
                "timestamp": datetime.now().isoformat()
            })

    def _check_consistency(self, arc: CharacterArc, chapter: int,
                          new_state: Dict[str, Any]):
        """检查一致性"""
        issues = []
        
        if not arc.snapshots:
            return
        
        last_snapshot = arc.snapshots[-1]
        
        # 1. 检查境界倒退
        realms_order = self._get_realms_order()
        if realms_order and last_snapshot.cultivation and new_state.get("cultivation"):
            old_idx = realms_order.index(last_snapshot.cultivation) if last_snapshot.cultivation in realms_order else -1
            new_idx = realms_order.index(new_state["cultivation"]) if new_state["cultivation"] in realms_order else -1
            
            if old_idx > 0 and new_idx >= 0 and new_idx < old_idx:
                # 境界倒退，需要特殊说明
                if new_state.get("status") not in ["injured", "poisoned", "weakened"]:
                    issues.append(f"境界从 {last_snapshot.cultivation} 倒退到 {new_state['cultivation']}，但状态为 {new_state.get('status', 'active')}")
        
        # 2. 检查性格突变
        if new_state.get("emotional_state") and last_snapshot.emotional_state:
            old_emotion = last_snapshot.emotional_state
            new_emotion = new_state["emotional_state"]
            
            # 极端变化警告（如 stable -> extremely angry）
            emotion_distance = self._emotion_distance(old_emotion, new_emotion)
            if emotion_distance > 2:
                issues.append(f"情绪状态从 {old_emotion} 剧变为 {new_emotion}，跨度过大")
        
        # 3. 检查道德立场突变
        if new_state.get("moral_alignment") and last_snapshot.moral_alignment:
            if new_state["moral_alignment"] != last_snapshot.moral_alignment:
                issues.append(f"道德立场从 {last_snapshot.moral_alignment} 变为 {new_state['moral_alignment']}")
        
        arc.is_consistent = len(issues) == 0
        arc.consistency_issues = issues
        
        if issues:
            logger.warning(f"角色 {arc.name} 弧光一致性问题: {'; '.join(issues)}")

    def _get_realms_order(self) -> List[str]:
        """获取境界等级顺序（从state.json读取）"""
        state_file = self.project_root / ".webnovel" / "state.json"
        if state_file.exists():
            try:
                state_data = json.loads(read_text_file(state_file))
                return state_data.get("world", {}).get("realms", [])
            except:
                pass
        return []

    def _emotion_distance(self, emotion1: str, emotion2: str) -> int:
        """计算情绪距离"""
        emotion_order = {
            "very_happy": 5,
            "happy": 4,
            "stable": 3,
            "anxious": 2,
            "angry": 1,
            "very_angry": 0
        }
        val1 = emotion_order.get(emotion1, 3)
        val2 = emotion_order.get(emotion2, 3)
        return abs(val1 - val2)

    def get_character_arc(self, name: str) -> Optional[CharacterArc]:
        """获取角色弧光"""
        return self.arcs.get(name)

    def get_all_arcs(self) -> Dict[str, CharacterArc]:
        """获取所有弧光"""
        return self.arcs

    def get_active_characters(self) -> List[str]:
        """获取活跃角色"""
        return list(self.arcs.keys())

    def get_arc_summary_for_context(self, name: str, recent_chapters: int = 5) -> str:
        """生成用于写作上下文的弧光摘要"""
        if name not in self.arcs:
            return f"（角色 {name} 无弧光记录）"
        
        arc = self.arcs[name]
        if not arc.snapshots:
            return f"（角色 {name} 无快照记录）"
        
        lines = [f"## {name} 角色弧光"]
        lines.append(f"- 角色定位: {arc.role}")
        lines.append(f"- 初始欲望: {arc.initial_desire}")
        lines.append(f"- 初始缺陷: {arc.initial_flaw}")
        
        # 最近状态
        recent_snapshots = arc.snapshots[-recent_chapters:]
        if recent_snapshots:
            last = recent_snapshots[-1]
            lines.append(f"\n### 当前状态（第{last.chapter}章）")
            lines.append(f"- 境界: {last.cultivation}")
            lines.append(f"- 状态: {last.status}")
            lines.append(f"- 情绪: {last.emotional_state}")
            lines.append(f"- 动机: {last.motivation}")
            if last.relationships:
                lines.append(f"- 关系: {', '.join(f'{k}:{v}' for k, v in list(last.relationships.items())[:5])}")
        
        # 最近转折点
        if arc.turning_points:
            recent_turning = arc.turning_points[-3:]
            lines.append(f"\n### 最近转折点")
            for tp in recent_turning:
                lines.append(f"- 第{tp['chapter']}章: {tp['description']}")
        
        # 一致性问题
        if arc.consistency_issues:
            lines.append(f"\n### ⚠️ 一致性问题")
            for issue in arc.consistency_issues:
                lines.append(f"- {issue}")
        
        return "\n".join(lines)

    def generate_audit_report(self, character_name: Optional[str] = None) -> str:
        """生成弧光审计报告"""
        lines = ["# 角色弧光审计报告\n"]
        lines.append(f"生成时间: {datetime.now().isoformat()}\n")
        
        characters_to_report = [character_name] if character_name else list(self.arcs.keys())
        
        for name in characters_to_report:
            if name not in self.arcs:
                continue
            
            arc = self.arcs[name]
            lines.append(f"\n## {name} ({arc.role})")
            lines.append(f"- 弧光类型: {arc.arc_type or '未定义'}")
            lines.append(f"- 快照数量: {len(arc.snapshots)}")
            lines.append(f"- 转折点数量: {len(arc.turning_points)}")
            lines.append(f"- 关系变化次数: {len(arc.relationship_history)}")
            lines.append(f"- 能力变化次数: {len(arc.power_progression)}")
            lines.append(f"- 一致性状态: {'✅ 一致' if arc.is_consistent else '❌ 存在问题'}")
            
            if arc.consistency_issues:
                lines.append(f"\n### 一致性问题")
                for issue in arc.consistency_issues:
                    lines.append(f"⚠️ {issue}")
            
            # 能力进展
            if arc.power_progression:
                lines.append(f"\n### 能力进展")
                for pp in arc.power_progression[-5:]:
                    lines.append(f"- 第{pp['chapter']}章: {pp['old_level']} → {pp['new_level']}")
            
            # 关系变化
            if arc.relationship_history:
                lines.append(f"\n### 最近关系变化")
                for rh in arc.relationship_history[-5:]:
                    lines.append(f"- 第{rh['chapter']}章: 与 {rh['character']} 从 '{rh['old_relation']}' 变为 '{rh['new_relation']}'")
            
            lines.append("")
        
        return "\n".join(lines)

    def check_character_consistency(self, name: str, chapter: int, 
                                   new_state: Dict[str, Any]) -> Dict[str, Any]:
        """检查角色一致性（供审查器调用）"""
        if name not in self.arcs:
            return {"consistent": True, "issues": [], "warnings": []}
        
        arc = self.arcs[name]
        issues = []
        warnings = []
        
        if not arc.snapshots:
            return {"consistent": True, "issues": [], "warnings": []}
        
        last_snapshot = arc.snapshots[-1]
        
        # 检查境界一致性
        if last_snapshot.cultivation and new_state.get("cultivation"):
            realms_order = self._get_realms_order()
            if realms_order:
                old_idx = realms_order.index(last_snapshot.cultivation) if last_snapshot.cultivation in realms_order else -1
                new_idx = realms_order.index(new_state["cultivation"]) if new_state["cultivation"] in realms_order else -1
                
                if old_idx > 0 and new_idx >= 0 and new_idx < old_idx:
                    if new_state.get("status") not in ["injured", "poisoned", "weakened"]:
                        issues.append({
                            "severity": "critical",
                            "description": f"{name} 的境界从 {last_snapshot.cultivation} 倒退为 {new_state['cultivation']}"
                        })
        
        # 检查关键物品一致性
        if last_snapshot.items and new_state.get("items"):
            lost_items = set(last_snapshot.items) - set(new_state["items"])
            if lost_items:
                warnings.append(f"{name} 失去了关键物品: {', '.join(lost_items)}")
        
        return {
            "consistent": len(issues) == 0,
            "issues": issues,
            "warnings": warnings
        }
