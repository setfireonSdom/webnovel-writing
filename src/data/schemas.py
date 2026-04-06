"""
数据模型定义
"""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class Genre(str, Enum):
    """题材类型"""
    XIANXIA = "仙侠"
    URBAN = "都市"
    GAME = "游戏"
    MYSTERY = "悬疑"
    FANTASY = "玄幻"
    SCIENCE_FICTION = "科幻"
    ROMANCE = "言情"
    HISTORICAL = "历史"


class StrandType(str, Enum):
    """情节线类型"""
    QUEST = "quest"  # 主线
    FIRE = "fire"  # 感情线
    CONSTELLATION = "constellation"  # 世界观线


class Severity(str, Enum):
    """问题严重性"""
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class Entity(BaseModel):
    """实体（角色、地点、势力等）"""
    name: str
    entity_type: str  # character, location, faction, item, etc.
    description: str = ""
    attributes: Dict[str, Any] = Field(default_factory=dict)
    first_appearance_chapter: int = 0
    last_appearance_chapter: int = 0
    status: str = "active"  # active, inactive, deceased


class ChapterMeta(BaseModel):
    """章节元数据"""
    chapter_num: int
    title: str = ""
    word_count: int = 0
    strand_type: StrandType = StrandType.QUEST
    hook_strength: float = 0.0  # 钩子强度 0-100
    cool_point_count: int = 0  # 爽点数量
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)


class ReviewIssue(BaseModel):
    """审查问题"""
    id: str
    severity: Severity
    category: str
    description: str
    location: str = ""
    suggestion: str = ""


class ReviewReport(BaseModel):
    """审查报告"""
    agent: str = "review-system"
    chapter: int
    overall_score: int = 0
    pass_: bool = False
    dimension_scores: Dict[str, int] = Field(default_factory=dict)
    severity_counts: Dict[str, int] = Field(default_factory=dict)
    issues: List[ReviewIssue] = Field(default_factory=list)
    summary: str = ""
    
    def to_rich_table(self) -> str:
        """生成 Rich 表格格式的字符串"""
        from rich.console import Console
        from rich.table import Table

        table = Table(title=f"审查报告 - 第 {self.chapter} 章")
        table.add_column("维度", style="cyan")
        table.add_column("评分", style="magenta")

        for dim, score in self.dimension_scores.items():
            table.add_row(dim, str(score))

        table.add_row("总分", str(self.overall_score))
        table.add_row("结果", "通过" if self.pass_ else "未通过")

        # 渲染表格
        console = Console(record=True, force_terminal=True, width=120)
        console.print(table)

        if self.issues:
            console.print(f"\n发现 {len(self.issues)} 个问题:")
            for issue in self.issues[:5]:  # 只显示前 5 个
                console.print(f"  [{issue.severity.value.upper()}] {issue.description}")

        return console.export_text()


class CharacterState(BaseModel):
    """角色状态快照 - 统一的角色数据模型"""
    name: str
    gender: str = ""  # 性别：男/女/其他，写作和检查器必须遵守
    cultivation: str = ""  # 修为境界
    status: str = "active"  # active, injured, deceased, etc.
    personality: str = ""  # 性格特征（如：冷酷、狡猾、热血）
    traits: List[str] = Field(default_factory=list)  # 角色特征标签
    background: str = ""  # 背景故事摘要
    relationships: Dict[str, str] = Field(default_factory=dict)  # 与他人的关系
    key_items: List[str] = Field(default_factory=list)  # 持有的关键物品
    knowledge: List[str] = Field(default_factory=list)  # 角色知道的关键信息（用于信息差追踪）
    aliases: List[str] = Field(default_factory=list)  # 别名/化名/称号
    notes: str = ""  # 其他备注


class ProjectState(BaseModel):
    """项目状态"""
    project: Dict[str, Any] = Field(default_factory=dict)
    protagonist: Dict[str, Any] = Field(default_factory=dict)
    world: Dict[str, Any] = Field(default_factory=dict)
    progress: Dict[str, Any] = Field(default_factory=dict)
    strands: Dict[str, float] = Field(default_factory=lambda: {
        "quest_ratio": 0.60,
        "fire_ratio": 0.25,
        "constellation_ratio": 0.15,
    })
    foreshadowing: List[Dict[str, Any]] = Field(default_factory=list)
    review_checkpoints: List[Dict[str, Any]] = Field(default_factory=list)
    entities: Dict[str, Any] = Field(default_factory=dict)
    reading_power: Dict[str, Any] = Field(default_factory=dict)
    
    # 新增：角色状态快照（自动更新）
    character_states: List[CharacterState] = Field(default_factory=list)
    
    # 新增：最近剧情摘要
    recent_summary: str = ""  # 最近一章的剧情摘要（200字内）


class WorkflowState(BaseModel):
    """工作流状态"""
    current_task: Optional[Dict[str, Any]] = None
    last_stable_state: Optional[Dict[str, Any]] = None
    history: List[Dict[str, Any]] = Field(default_factory=list)


class ChapterResult(BaseModel):
    """章节写作结果"""
    success: bool
    chapter_num: int
    file_path: str = ""
    word_count: int = 0
    error: str = ""
    review_report: Optional[ReviewReport] = None
