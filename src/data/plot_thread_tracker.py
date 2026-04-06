"""
剧情线追踪器 (Plot Thread Tracker)
职责：显式管理长篇小说中的伏笔、悬念、未决冲突。
解决 AI“挖坑不填”或“忘了填坑”的问题。
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional, Literal
from pydantic import BaseModel, Field

from ..utils.file_ops import atomic_write_json, read_json

logger = logging.getLogger(__name__)

ThreadStatus = Literal["open", "resolved", "abandoned"]

class PlotThread(BaseModel):
    """剧情线/伏笔"""
    id: str
    description: str  # 伏笔描述
    type: str = "foreshadowing"  # foreshadowing, conflict, mystery, promise
    created_chapter: int
    status: ThreadStatus = "open"
    
    # 追踪信息
    related_chapters: List[int] = Field(default_factory=list)
    last_mentioned_chapter: int = 0
    expected_payoff_chapter: Optional[int] = None  # 预期回收章节
    priority: str = "medium"  # low, medium, high, critical
    
    # 状态变更
    resolved_chapter: Optional[int] = None
    resolution_summary: str = ""

    @property
    def age(self) -> int:
        """存在了多少章"""
        return self.last_mentioned_chapter - self.created_chapter

    @property
    def is_overdue(self) -> bool:
        """是否超期未填"""
        if self.status != "open":
            return False
        if self.expected_payoff_chapter and self.last_mentioned_chapter > self.expected_payoff_chapter + 10:
            return True
        # 超过 50 章未提及且未解决，视为可能被遗忘
        if self.last_mentioned_chapter > 0 and self.last_mentioned_chapter - self.created_chapter > 50:
            return True
        return False


class PlotThreadTracker:
    """剧情线管理器"""

    def __init__(self, project_root: Path):
        self.project_root = project_root
        self.data_file = project_root / ".webnovel" / "plot_threads.json"
        self.data_file.parent.mkdir(parents=True, exist_ok=True)
        
        self.threads: Dict[str, PlotThread] = {}
        self._load()

    def _load(self):
        """加载数据"""
        if self.data_file.exists():
            try:
                data = read_json(self.data_file)
                for tid, t_data in data.get("threads", {}).items():
                    self.threads[tid] = PlotThread(**t_data)
            except Exception as e:
                logger.error(f"加载剧情线数据失败: {e}")
                self.threads = {}

    def _save(self):
        """保存数据"""
        try:
            data = {
                "threads": {tid: t.model_dump() for tid, t in self.threads.items()},
                "last_updated": datetime.now().isoformat(),
            }
            atomic_write_json(self.data_file, data)
        except Exception as e:
            logger.error(f"保存剧情线数据失败: {e}")

    def add_thread(self, chapter_num: int, description: str, 
                   p_type: str = "foreshadowing", priority: str = "medium",
                   expected_payoff_chapter: Optional[int] = None) -> str:
        """添加新剧情线"""
        import uuid
        thread_id = f"thread_{uuid.uuid4().hex[:8]}"
        
        thread = PlotThread(
            id=thread_id,
            description=description,
            type=p_type,
            created_chapter=chapter_num,
            last_mentioned_chapter=chapter_num,
            priority=priority,
            expected_payoff_chapter=expected_payoff_chapter,
        )
        
        self.threads[thread_id] = thread
        self._save()
        logger.info(f"新建剧情线: {description} (ID: {thread_id})")
        return thread_id

    def update_thread(self, thread_id: str, chapter_num: int, 
                      status: Optional[ThreadStatus] = None,
                      summary: str = ""):
        """更新剧情线状态"""
        if thread_id not in self.threads:
            logger.warning(f"剧情线不存在: {thread_id}")
            return

        thread = self.threads[thread_id]
        thread.last_mentioned_chapter = chapter_num
        
        if chapter_num not in thread.related_chapters:
            thread.related_chapters.append(chapter_num)

        if status:
            thread.status = status
            if status == "resolved":
                thread.resolved_chapter = chapter_num
                thread.resolution_summary = summary
        
        self._save()

    def get_active_threads(self, min_priority: str = "low") -> List[PlotThread]:
        """获取活跃的剧情线"""
        priority_map = {"low": 0, "medium": 1, "high": 2, "critical": 3}
        min_level = priority_map.get(min_priority, 0)
        
        return [
            t for t in self.threads.values()
            if t.status == "open" and priority_map.get(t.priority, 0) >= min_level
        ]

    def get_overdue_threads(self) -> List[PlotThread]:
        """获取超期/可能被遗忘的剧情线"""
        return [t for t in self.threads.values() if t.is_overdue and t.status == "open"]

    def generate_reminder_prompt(self, current_chapter: int) -> str:
        """生成 AI 提醒提示词"""
        active = self.get_active_threads(min_priority="medium")
        overdue = self.get_overdue_threads()
        
        if not active and not overdue:
            return ""
        
        lines = ["\n\n## 🧵 活跃剧情线与伏笔提醒 (必须关注)"]
        
        if overdue:
            lines.append("### ⚠️ 超期未回收的伏笔（请尝试在本章或近期回收）：")
            for t in overdue:
                lines.append(f"- 【超期】{t.description} (埋于第 {t.created_chapter} 章, {t.age} 章未提及)")
        
        if active:
            lines.append("### 🔹 正在进行的剧情线（请保持逻辑呼应）：")
            # 按优先级排序
            priority_map = {"low": 0, "medium": 1, "high": 2, "critical": 3}
            active.sort(key=lambda x: priority_map.get(x.priority, 0), reverse=True)
            for t in active[:5]:  # 最多提醒 5 个
                lines.append(f"- {t.description} (优先级: {t.priority})")
        
        return "\n".join(lines)
