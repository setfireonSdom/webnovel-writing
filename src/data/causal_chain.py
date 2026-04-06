"""
因果链追踪器 - 用代码追踪"谁欠谁"、"什么伏笔没填"
职责：
1. 记录因果债（A 救了 B → B 欠 A 一条命）
2. 追踪伏笔状态（开启、推进、回收）
3. 强制回收到期未还的债
"""

import json
import logging
from enum import Enum
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from ..utils.file_ops import read_text_file, atomic_write_json, ensure_directory

logger = logging.getLogger(__name__)


class CausalDebt(BaseModel):
    """因果债"""
    id: str
    debtor: str  # 欠债人
    creditor: str  # 债权人
    debt_type: str  # 救命之恩、金钱、感情、承诺等
    description: str  # 欠了什么
    created_chapter: int  # 何时欠的
    urgency: int = 50  # 紧急度 0-100
    is_paid: bool = False  # 是否已还
    paid_chapter: Optional[int] = None  # 何时还的
    notes: str = ""


class ForeshadowingState(str, Enum):
    """伏笔状态"""
    OPEN = "开启"
    ACTIVE = "推进中"
    RESOLVED = "已回收"
    ABANDONED = "已放弃"


class Foreshadowing(BaseModel):
    """伏笔"""
    id: str
    description: str  # 伏笔内容
    type: str  # 悬念、冲突、关系、物品等
    created_chapter: int  # 何时埋的
    expected_resolve_chapter: Optional[int] = None  # 预计回收章节
    state: ForeshadowingState = ForeshadowingState.OPEN
    last_mentioned_chapter: int = 0  # 最后一次提到
    resolved_chapter: Optional[int] = None  # 回收章节
    notes: str = ""


class CausalChainTracker:
    """因果链追踪器"""

    def __init__(self, project_root: Path):
        self.project_root = Path(project_root)
        self.webnovel_dir = self.project_root / ".webnovel"
        self.causal_file = self.webnovel_dir / "causal_chain.json"
        
        ensure_directory(self.webnovel_dir)
        
        # 加载数据
        self.debts: Dict[str, CausalDebt] = {}
        self.foreshadowings: Dict[str, Foreshadowing] = {}
        self._load_data()
    
    def _load_data(self):
        """加载数据"""
        if self.causal_file.exists():
            try:
                data = json.loads(read_text_file(self.causal_file))
                self.debts = {
                    did: CausalDebt(**d) 
                    for did, d in data.get("debts", {}).items()
                }
                self.foreshadowings = {
                    fid: Foreshadowing(**f) 
                    for fid, f in data.get("foreshadowings", {}).items()
                }
            except Exception as e:
                logger.warning(f"加载因果链失败: {e}")
    
    def _save_data(self):
        """保存数据"""
        data = {
            "debts": {did: d.model_dump() for did, d in self.debts.items()},
            "foreshadowings": {fid: f.model_dump() for fid, f in self.foreshadowings.items()},
            "last_updated": datetime.now().isoformat()
        }
        atomic_write_json(self.causal_file, data)
    
    # ===== 因果债管理 =====
    
    def add_debt(
        self, 
        debtor: str, 
        creditor: str, 
        debt_type: str, 
        description: str,
        chapter_num: int,
        urgency: int = 50
    ) -> str:
        """添加因果债"""
        debt_id = f"DEBT_{len(self.debts) + 1:04d}"
        debt = CausalDebt(
            id=debt_id,
            debtor=debtor,
            creditor=creditor,
            debt_type=debt_type,
            description=description,
            created_chapter=chapter_num,
            urgency=urgency
        )
        self.debts[debt_id] = debt
        self._save_data()
        logger.info(f"添加因果债: {debtor} 欠 {creditor} {description}")
        return debt_id
    
    def pay_debt(self, debt_id: str, chapter_num: int) -> bool:
        """还债"""
        if debt_id not in self.debts:
            return False
        debt = self.debts[debt_id]
        debt.is_paid = True
        debt.paid_chapter = chapter_num
        self._save_data()
        logger.info(f"因果债已还: {debt.description}")
        return True
    
    def get_unpaid_debts(self, character_name: str = None) -> List[CausalDebt]:
        """获取未还的债"""
        debts = [d for d in self.debts.values() if not d.is_paid]
        if character_name:
            debts = [d for d in debts if d.debtor == character_name or d.creditor == character_name]
        return sorted(debts, key=lambda x: x.urgency, reverse=True)
    
    def get_overdue_debts(self, current_chapter: int, threshold: int = 30) -> List[CausalDebt]:
        """获取超期未还的债"""
        return [
            d for d in self.debts.values()
            if not d.is_paid and (current_chapter - d.created_chapter) > threshold
        ]
    
    # ===== 伏笔管理 =====
    
    def add_foreshadowing(
        self,
        description: str,
        chapter_num: int,
        f_type: str = "悬念",
        expected_resolve_chapter: Optional[int] = None
    ) -> str:
        """添加伏笔"""
        fid = f"FS_{len(self.foreshadowings) + 1:04d}"
        fs = Foreshadowing(
            id=fid,
            description=description,
            type=f_type,
            created_chapter=chapter_num,
            expected_resolve_chapter=expected_resolve_chapter,
            last_mentioned_chapter=chapter_num
        )
        self.foreshadowings[fid] = fs
        self._save_data()
        logger.info(f"添加伏笔: {description}")
        return fid
    
    def update_foreshadowing(
        self,
        foreshadowing_id: str,
        chapter_num: int,
        state: Optional[ForeshadowingState] = None,
        notes: str = ""
    ) -> bool:
        """更新伏笔"""
        if foreshadowing_id not in self.foreshadowings:
            return False
        fs = self.foreshadowings[foreshadowing_id]
        fs.last_mentioned_chapter = chapter_num
        if state:
            fs.state = state
        if notes:
            fs.notes = notes
        if state == ForeshadowingState.RESOLVED:
            fs.resolved_chapter = chapter_num
        self._save_data()
        return True
    
    def resolve_foreshadowing(self, foreshadowing_id: str, chapter_num: int) -> bool:
        """回收伏笔"""
        return self.update_foreshadowing(
            foreshadowing_id, 
            chapter_num, 
            state=ForeshadowingState.RESOLVED
        )
    
    def get_active_foreshadowings(self) -> List[Foreshadowing]:
        """获取活跃的伏笔"""
        return [
            f for f in self.foreshadowings.values()
            if f.state in [ForeshadowingState.OPEN, ForeshadowingState.ACTIVE]
        ]
    
    def get_overdue_foreshadowings(self, current_chapter: int, threshold: int = 50) -> List[Foreshadowing]:
        """获取超期未回收的伏笔"""
        return [
            f for f in self.foreshadowings.values()
            if f.state in [ForeshadowingState.OPEN, ForeshadowingState.ACTIVE]
            and (current_chapter - f.created_chapter) > threshold
        ]
    
    # ===== 写作约束生成 =====
    
    def generate_writing_constraints(self, current_chapter: int) -> str:
        """生成写作约束（强制AI关注）"""
        lines = ["## 📌 因果链约束（必须遵守）"]
        
        # 1. 超期未还的债
        overdue_debts = self.get_overdue_debts(current_chapter, threshold=30)
        if overdue_debts:
            lines.append("\n### 紧急：以下因果债已超期，必须在后续章节中回收")
            for debt in overdue_debts[:5]:
                lines.append(f"- {debt.debtor} 欠 {debt.creditor} {debt.debt_type}: {debt.description}")
                lines.append(f"  埋于第{debt.created_chapter}章，已逾期{current_chapter - debt.created_chapter}章")
        
        # 2. 超期未回收的伏笔
        overdue_fs = self.get_overdue_foreshadowings(current_chapter, threshold=50)
        if overdue_fs:
            lines.append("\n### 警告：以下伏笔已超期，必须尽快回收")
            for fs in overdue_fs[:5]:
                lines.append(f"- [{fs.type}] {fs.description}")
                lines.append(f"  埋于第{fs.created_chapter}章，已{current_chapter - fs.created_chapter}章未回收")
        
        # 3. 活跃伏笔列表
        active_fs = self.get_active_foreshadowings()
        if active_fs:
            lines.append(f"\n### 当前活跃伏笔（写作时请注意呼应）")
            for fs in active_fs[:10]:
                status = "开启" if fs.state == ForeshadowingState.OPEN else "推进中"
                lines.append(f"- [{status}] {fs.description}")
        
        if not overdue_debts and not overdue_fs and not active_fs:
            lines.append("\n（暂无因果链约束）")
        
        return "\n".join(lines)
    
    def analyze_chapter_for_debts_and_foreshadowings(
        self, 
        chapter_num: int, 
        text_content: str,
        llm=None
    ) -> Dict[str, Any]:
        """分析章节，自动提取新的因果债和伏笔"""
        results = {
            "new_debts": [],
            "paid_debts": [],
            "new_foreshadowings": [],
            "resolved_foreshadowings": []
        }
        
        if llm:
            # 使用AI提取
            extraction = self._extract_with_ai(chapter_num, text_content, llm)
            
            # 添加新债
            for debt in extraction.get("new_debts", []):
                debt_id = self.add_debt(
                    debtor=debt.get("debtor"),
                    creditor=debt.get("creditor"),
                    debt_type=debt.get("type"),
                    description=debt.get("description"),
                    chapter_num=chapter_num,
                    urgency=debt.get("urgency", 50)
                )
                results["new_debts"].append(debt_id)
            
            # 还债
            for paid in extraction.get("paid_debts", []):
                debt_id = paid.get("debt_id")
                if debt_id in self.debts:
                    self.pay_debt(debt_id, chapter_num)
                    results["paid_debts"].append(debt_id)
            
            # 添加新伏笔
            for fs in extraction.get("new_foreshadowings", []):
                fs_id = self.add_foreshadowing(
                    description=fs.get("description"),
                    chapter_num=chapter_num,
                    f_type=fs.get("type"),
                    expected_resolve_chapter=fs.get("expected_resolve_chapter")
                )
                results["new_foreshadowings"].append(fs_id)
            
            # 回收伏笔
            for resolved in extraction.get("resolved_foreshadowings", []):
                fs_id = resolved.get("foreshadowing_id")
                if fs_id in self.foreshadowings:
                    self.resolve_foreshadowing(fs_id, chapter_num)
                    results["resolved_foreshadowings"].append(fs_id)
        
        return results
    
    def _extract_with_ai(self, chapter_num: int, text: str, llm) -> Dict[str, Any]:
        """使用AI提取因果链变化"""
        # 这里调用LLM提取
        pass
