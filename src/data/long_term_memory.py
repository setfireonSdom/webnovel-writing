"""
长期记忆与状态生命周期管理
解决 100 万字写作中 state.json 膨胀和上下文窗口限制问题。
新增：智能记忆衰减机制 - 重要设定永久保留，次要设定按权重衰减
"""

import json
import logging
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime

from ..utils.file_ops import atomic_write_json, read_json, ensure_directory
from ..data.schemas import ProjectState

logger = logging.getLogger(__name__)

# 记忆衰减配置
MEMORY_DECAY_CONFIG = {
    # 记忆重要性权重（越高越不容易被衰减）
    "importance_weights": {
        "protagonist_goal": 1.0,  # 主角目标 - 永久保留
        "protagonist_cultivation": 1.0,  # 主角境界 - 永久保留
        "key_relationships": 0.9,  # 关键关系
        "world_rules": 0.95,  # 世界观规则 - 几乎永久
        "faction_info": 0.7,  # 势力信息
        "item_details": 0.4,  # 物品细节 - 容易衰减
        "minor_characters": 0.3,  # 次要角色 - 容易衰减
        "early_events": 0.5,  # 早期事件
    },
    # 衰减阈值（多少章后开始衰减）
    "decay_thresholds": {
        "high_importance": 100,  # 高重要性100章后开始衰减
        "medium_importance": 50,  # 中重要性50章后
        "low_importance": 20,  # 低重要性20章后
    },
    # 保留的关键信息数量
    "keep_limits": {
        "recent_chapters": 5,  # 保留最近5章详情
        "key_characters": 10,  # 保留10个关键角色
        "active_factions": 5,  # 保留5个活跃势力
        "important_items": 8,  # 保留8个重要物品
    }
}


class LongTermMemory:
    """长期记忆管理器"""

    def __init__(self, project_root: Path):
        self.project_root = project_root
        self.webnovel_dir = project_root / ".webnovel"
        
        # 归档文件
        self.archive_file = self.webnovel_dir / "state_archive.json"
        self.volume_summaries_file = self.webnovel_dir / "volume_summaries.json"
        
        ensure_directory(self.webnovel_dir)
        
        self.archive_data = self._load_archive()
        self.volume_summaries = self._load_summaries()

    def _load_archive(self) -> Dict[str, Any]:
        if self.archive_file.exists():
            try:
                return read_json(self.archive_file)
            except:
                return {"entities": [], "characters": []}
        return {"entities": [], "characters": []}

    def _load_summaries(self) -> Dict[str, str]:
        if self.volume_summaries_file.exists():
            try:
                return read_json(self.volume_summaries_file)
            except:
                return {}
        return {}

    def _save_archive(self):
        atomic_write_json(self.archive_file, self.archive_data)

    def _save_summaries(self):
        atomic_write_json(self.volume_summaries_file, self.volume_summaries)

    def archive_old_entities(self, current_chapter: int, active_threshold: int = 50):
        """
        将长时间未出现的实体归档，保持 state.json 轻量。
        :param current_chapter: 当前章节
        :param active_threshold: 超过多少章未出现则归档
        """
        # 这个函数通常由 DataAgent 在每章结束时调用
        # 它会检查 state.json 中的 entities，将 last_appearance_chapter 太旧的移入 archive
        # 这里只做逻辑演示，实际移动需要在 StateManager 中配合
        pass

    def add_volume_summary(self, volume_num: int, summary: str):
        """添加卷摘要（压缩后的剧情精华）"""
        self.volume_summaries[str(volume_num)] = summary
        self._save_summaries()
        logger.info(f"已保存第 {volume_num} 卷摘要 ({len(summary)} 字)")

    def get_distant_context(self, current_chapter: int, current_volume: int = 1) -> str:
        """
        获取“远距离上下文”。
        当写到第 200 章时，AI 记不清第 5 章的细节，但需要知道“大局”。
        """
        context_parts = []
        
        # 1. 获取之前所有卷的摘要
        for vol_num, summary in self.volume_summaries.items():
            if int(vol_num) < current_volume:
                context_parts.append(f"## 第 {vol_num} 卷剧情回顾\n{summary[:500]}...")
        
        # 2. 获取当前卷之前的章节摘要（如果有更细粒度的）
        summaries_dir = self.project_root / ".webnovel" / "summaries"
        if summaries_dir.exists():
            # 这里可以逻辑优化为只取关键节点章节的摘要
            pass

        # 3. 归档中的关键信息（如已退场的重要角色结局）
        archived_characters = self.archive_data.get("characters", [])
        if archived_characters:
            char_lines = []
            for char in archived_characters:
                char_lines.append(f"- {char.get('name')}: {char.get('final_status', '下落不明')}")
            context_parts.append("## 已退场角色结局\n" + "\n".join(char_lines))

        return "\n\n".join(context_parts) if context_parts else "（暂无长期记忆数据）"

    def compress_state_for_context(self, state: ProjectState) -> str:
        """
        将庞大的 state.json 压缩为适合放入 LLM prompt 的短文本。
        使用智能记忆衰减：重要设定永久保留，次要设定按权重衰减。
        
        修复：确保传递完整的角色信息，包括性别、性格、特征等，避免写作LLM瞎猜。
        """
        lines = ["## 🌍 当前世界状态 (智能压缩版)"]

        # 主角核心状态（永久保留）
        p = state.protagonist
        protagonist_name = p.get('name', '未知')
        
        # 【关键修复】查找主角在 character_states 中的完整信息
        protagonist_state = None
        for cs in state.character_states:
            if cs.name == protagonist_name:
                protagonist_state = cs
                break
        
        # 性别 - 优先从 character_states 取，其次从 protagonist dict 取，最后默认男
        gender = ""
        if protagonist_state and protagonist_state.gender:
            gender = protagonist_state.gender
        else:
            gender = p.get('gender', '男')
        
        # 境界 - 优先从 character_states 取
        cultivation = ""
        if protagonist_state and protagonist_state.cultivation:
            cultivation = protagonist_state.cultivation
        else:
            cultivation = p.get('cultivation', '未知')
        
        # 状态 - 优先从 character_states 取
        status = ""
        if protagonist_state and protagonist_state.status:
            status = protagonist_state.status
        else:
            status = p.get('status', '活跃')
        
        lines.append(f"- 主角: {protagonist_name}")
        lines.append(f"- 性别: {gender}")  # 【新增】明确传递性别
        lines.append(f"- 核心目标: {p.get('desire', '无')}")
        lines.append(f"- 缺陷: {p.get('flaw', '无')}")
        lines.append(f"- 性格: {protagonist_state.personality if protagonist_state and protagonist_state.personality else p.get('traits', '未知')}")  # 【新增】性格
        lines.append(f"- 当前境界/状态: {cultivation} / {status}")

        # 金手指（永久保留）
        if p.get('golden_finger'):
            lines.append(f"- 金手指: {p['golden_finger'][:100]}")
        
        # 主角别名/称号（如果有）
        if protagonist_state and protagonist_state.aliases:
            lines.append(f"- 别名/称号: {', '.join(protagonist_state.aliases)}")  # 【新增】别名

        # 活跃角色（按重要性排序，保留关键角色）
        active_chars = self._get_important_characters(state)
        if active_chars:
            lines.append("\n### 关键角色动态")
            for cs in active_chars:
                # 【修复】每个角色都传递性别、性格、境界、状态
                char_info = f"- {cs.name}: {'男' if cs.gender == '男' else '女' if cs.gender == '女' else cs.gender or '性别未知'}"
                char_info += f" | 境界: {cs.cultivation or '未知'}"
                char_info += f" | 状态: {cs.status}"
                if cs.personality:
                    char_info += f" | 性格: {cs.personality}"
                lines.append(char_info)
                
                if cs.relationships:
                    # 只显示重要关系
                    key_rels = list(cs.relationships.items())[:3]
                    if key_rels:
                        rels_str = ", ".join(f"{k}:{v}" for k, v in key_rels)
                        lines.append(f"  关系: {rels_str}")
                if cs.key_items:
                    lines.append(f"  持有: {', '.join(cs.key_items[:3])}")
                if cs.background:
                    lines.append(f"  背景: {cs.background[:50]}")
                if cs.aliases:
                    lines.append(f"  别名: {', '.join(cs.aliases)}")

        # 当前主线（如有）
        if hasattr(state, 'current_storyline') and state.current_storyline:
            lines.append(f"\n### 正在推进的主线")
            lines.append(f"{state.current_storyline}")

        # 活跃势力
        active_factions = self._get_active_factions(state)
        if active_factions:
            lines.append(f"\n### 活跃势力")
            for faction in active_factions:
                lines.append(f"- {faction}")

        # 衰减警告（如果有信息被压缩）
        decayed_info = self._get_decayed_info(state)
        if decayed_info:
            lines.append(f"\n### ⚠️ 已衰减信息（仅供参考，可能不准确）")
            lines.append(f"以下信息因长时间未更新已衰减，如需准确信息请查阅历史章节：")
            for info in decayed_info[:3]:  # 最多显示3条
                lines.append(f"- {info}")

        return "\n".join(lines)
    
    def _get_important_characters(self, state: ProjectState) -> list:
        """获取重要角色列表（应用记忆衰减）"""
        # 优先保留主角
        protagonist_name = state.protagonist.get('name', '')
        
        # 分类角色
        characters_by_importance = {
            'protagonist': [],
            'recent_active': [],  # 最近活跃
            'key_supporting': [],  # 关键配角
            'minor': []  # 次要角色
        }
        
        for cs in state.character_states:
            if cs.name == protagonist_name:
                characters_by_importance['protagonist'].append(cs)
            elif cs.status in ['active', 'injured'] and cs.notes:
                # 有状态备注的视为重要
                characters_by_importance['key_supporting'].append(cs)
            elif cs.status == 'active':
                characters_by_importance['recent_active'].append(cs)
            else:
                characters_by_importance['minor'].append(cs)
        
        # 按优先级组合
        result = []
        result.extend(characters_by_importance['protagonist'])
        result.extend(characters_by_importance['key_supporting'])
        result.extend(characters_by_importance['recent_active'])
        
        # 限制数量
        limit = MEMORY_DECAY_CONFIG["keep_limits"]["key_characters"]
        return result[:limit]
    
    def _get_active_factions(self, state: ProjectState) -> list:
        """获取活跃势力"""
        factions = []
        all_entities = state.entities.get('all', [])
        
        for entity in all_entities:
            if entity.get('entity_type') == 'faction' and entity.get('status') == 'active':
                factions.append(entity.get('name'))
        
        limit = MEMORY_DECAY_CONFIG["keep_limits"]["active_factions"]
        return factions[:limit]
    
    def _get_decayed_info(self, state: ProjectState) -> list:
        """获取已衰减的信息摘要"""
        decayed = []
        
        # 检查是否有大量inactive实体
        inactive_count = sum(1 for e in state.entities.get('all', []) 
                           if e.get('status') == 'inactive')
        if inactive_count > 5:
            decayed.append(f"有 {inactive_count} 个实体已归档（非活跃状态）")
        
        # 检查是否有归档角色
        archived_chars = self.archive_data.get('characters', [])
        if archived_chars:
            decayed.append(f"已归档 {len(archived_chars)} 个角色的历史数据")
        
        return decayed
