"""
状态管理器
管理项目状态文件和 SQLite 数据库
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from ..data.schemas import ProjectState, WorkflowState, Entity
from ..utils.file_ops import atomic_write_json, read_json, ensure_directory

logger = logging.getLogger(__name__)


class StateManager:
    """管理项目状态"""
    
    def __init__(self, project_root: Path):
        self.project_root = Path(project_root)
        self.webnovel_dir = self.project_root / ".webnovel"
        self.state_file = self.webnovel_dir / "state.json"
        self.workflow_state_file = self.webnovel_dir / "workflow_state.json"
        self.db_path = self.webnovel_dir / "index.db"
        
        ensure_directory(self.webnovel_dir)
    
    def load_state(self) -> ProjectState:
        """加载项目状态"""
        if self.state_file.exists():
            data = read_json(self.state_file)
            return ProjectState(**data)
        
        # 返回默认状态
        return ProjectState()
    
    def save_state(self, state: ProjectState):
        """保存项目状态"""
        atomic_write_json(self.state_file, state.model_dump())
        logger.debug(f"状态已保存到 {self.state_file}")
    
    def load_workflow_state(self) -> WorkflowState:
        """加载工作流状态"""
        if self.workflow_state_file.exists():
            data = read_json(self.workflow_state_file)
            return WorkflowState(**data)
        return WorkflowState()
    
    def save_workflow_state(self, state: WorkflowState):
        """保存工作流状态"""
        atomic_write_json(self.workflow_state_file, state.model_dump())
        logger.debug(f"工作流状态已保存到 {self.workflow_state_file}")
    
    def get_current_chapter(self) -> int:
        """获取当前章节号"""
        state = self.load_state()
        return state.progress.get("current_chapter", 0)
    
    def update_progress(self, chapter_num: int):
        """更新进度"""
        state = self.load_state()
        state.progress["current_chapter"] = chapter_num
        state.progress["last_updated"] = datetime.now().isoformat()
        self.save_state(state)
    
    def add_entity(self, entity: Entity):
        """添加实体"""
        state = self.load_state()
        entities = state.entities.setdefault("all", [])
        
        # 检查是否已存在
        for i, e in enumerate(entities):
            if e.get("name") == entity.name and e.get("entity_type") == entity.entity_type:
                entities[i] = entity.model_dump()
                self.save_state(state)
                return
        
        entities.append(entity.model_dump())
        self.save_state(state)
    
    def get_entities(self, entity_type: Optional[str] = None) -> List[Entity]:
        """获取实体列表"""
        state = self.load_state()
        entities = state.entities.get("all", [])
        
        if entity_type:
            entities = [e for e in entities if e.get("entity_type") == entity_type]
        
        return [Entity(**e) for e in entities]
    
    def add_review_checkpoint(self, chapter_num: int, score: int, passed: bool):
        """添加审查检查点"""
        state = self.load_state()
        state.review_checkpoints.append({
            "chapter": chapter_num,
            "score": score,
            "passed": passed,
            "timestamp": datetime.now().isoformat(),
        })
        self.save_state(state)
