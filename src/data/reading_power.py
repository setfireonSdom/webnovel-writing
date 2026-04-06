"""
追读力系统
职责：Hook/Cool-point/微兑现/债务追踪

债务机制：
- 未兑现的承诺会产生债务
- 每章累积 10% 利息
- 有明确的兑现截止期限
- 超期未偿还会影响追读力评分
"""

import logging
import json
from datetime import datetime
from typing import Dict, Any, List, Optional
from pathlib import Path
from dataclasses import dataclass, field, asdict

from ..utils.file_ops import read_json, atomic_write_json, ensure_directory

logger = logging.getLogger(__name__)


@dataclass
class Hook:
    """钩子"""
    type: str  # 悬念/危机/欲望/情感/选择/反转/信息差
    strength: int  # 1-100
    description: str
    chapter_num: int
    anchor: str = ""  # 钩子锚点（读者想知道什么）


@dataclass
class CoolPoint:
    """爽点"""
    type: str  # 装逼打脸/扮猪吃虎/越级反杀/打脸权威/反派翻车/甜蜜超预期/迪化误解/身份掉马
    intensity: str  # low/medium/high/explosive
    description: str
    chapter_num: int


@dataclass
class MicroPayoff:
    """微兑现"""
    description: str
    chapter_num: int
    debt_cleared: str = ""  # 清偿的债务描述


@dataclass
class Debt:
    """债务"""
    description: str  # 承诺描述
    chapter_created: int  # 创建章节
    chapter_due: int  # 截止章节
    interest_rate: float = 0.1  # 每章利息 10%
    is_paid: bool = False
    chapter_paid: Optional[int] = None


class ReadingPowerTracker:
    """追读力追踪器"""

    def __init__(self, project_root: Path):
        self.project_root = project_root
        self.data_file = project_root / ".webnovel" / "reading_power.json"
        ensure_directory(self.data_file.parent)

        self.hooks: List[Hook] = []
        self.cool_points: List[CoolPoint] = []
        self.micro_payoffs: List[MicroPayoff] = []
        self.debts: List[Debt] = []
        
        self._load()

    def _load(self):
        """加载数据"""
        if self.data_file.exists():
            try:
                data = read_json(self.data_file)
                self.hooks = [Hook(**h) for h in data.get("hooks", [])]
                self.cool_points = [CoolPoint(**cp) for cp in data.get("cool_points", [])]
                self.micro_payoffs = [MicroPayoff(**mp) for mp in data.get("micro_payoffs", [])]
                self.debts = [Debt(**d) for d in data.get("debts", [])]
                logger.info(f"追读力数据加载成功，共 {len(self.hooks)} 个钩子, {len(self.debts)} 个债务")
            except Exception as e:
                logger.error(f"加载追读力数据失败: {e}")
                self.hooks = []
                self.cool_points = []
                self.micro_payoffs = []
                self.debts = []

    def _save(self):
        """保存数据"""
        try:
            data = {
                "hooks": [asdict(h) for h in self.hooks],
                "cool_points": [asdict(cp) for cp in self.cool_points],
                "micro_payoffs": [asdict(mp) for mp in self.micro_payoffs],
                "debts": [asdict(d) for d in self.debts],
                "last_updated": datetime.now().isoformat(),
            }
            atomic_write_json(self.data_file, data)
        except Exception as e:
            logger.error(f"保存追读力数据失败: {e}")

    def add_hook(self, hook: Hook):
        """添加钩子"""
        self.hooks.append(hook)
        self._save()

    def add_cool_point(self, cool_point: CoolPoint):
        """添加爽点"""
        self.cool_points.append(cool_point)
        self._save()

    def add_micro_payoff(self, payoff: MicroPayoff):
        """添加微兑现"""
        self.micro_payoffs.append(payoff)
        
        # 如果有债务被清偿，标记为已支付
        if payoff.debt_cleared:
            for debt in self.debts:
                if debt.description == payoff.debt_cleared and not debt.is_paid:
                    debt.is_paid = True
                    debt.chapter_paid = payoff.chapter_num
                    logger.info(f"债务已清偿: {debt.description}")
        
        self._save()

    def add_debt(self, debt: Debt):
        """添加债务"""
        self.debts.append(debt)
        self._save()

    def calculate_interest(self, current_chapter: int) -> float:
        """计算当前总利息"""
        total_interest = 0.0
        for debt in self.debts:
            if not debt.is_paid:
                chapters_overdue = max(0, current_chapter - debt.chapter_due)
                interest = debt.interest_rate * chapters_overdue
                total_interest += interest
        return total_interest

    def get_active_debts(self, current_chapter: int) -> List[Debt]:
        """获取活跃债务"""
        return [
            debt for debt in self.debts
            if not debt.is_paid and current_chapter >= debt.chapter_due
        ]

    def get_overdue_debts(self, current_chapter: int) -> List[Debt]:
        """获取超期债务"""
        return [
            debt for debt in self.debts
            if not debt.is_paid and current_chapter > debt.chapter_due + 5  # 超过5章未还
        ]

    def evaluate_chapter(self, chapter_num: int, hook_strength: int, cool_point_count: int) -> Dict[str, Any]:
        """评估单章的追读力"""
        # 计算基础得分
        hook_score = hook_strength
        cool_point_score = min(cool_point_count * 20, 100)  # 每个爽点 20 分，最多 100
        
        # 债务惩罚
        active_debts = self.get_active_debts(chapter_num)
        overdue_debts = self.get_overdue_debts(chapter_num)
        debt_penalty = len(active_debts) * 10 + len(overdue_debts) * 20
        
        # 利息惩罚
        interest = self.calculate_interest(chapter_num)
        interest_penalty = min(int(interest * 100), 50)  # 最多扣 50 分
        
        # 综合得分
        base_score = (hook_score * 0.6 + cool_point_score * 0.4)
        final_score = max(0, base_score - debt_penalty - interest_penalty)

        return {
            "chapter_num": chapter_num,
            "hook_score": hook_score,
            "cool_point_score": cool_point_score,
            "debt_penalty": debt_penalty,
            "interest_penalty": interest_penalty,
            "final_score": int(final_score),
            "active_debts": len(active_debts),
            "overdue_debts": len(overdue_debts),
        }

    def get_summary(self, current_chapter: int) -> Dict[str, Any]:
        """获取追读力总结"""
        recent_hooks = [h for h in self.hooks if h.chapter_num > current_chapter - 10]
        recent_cool_points = [cp for cp in self.cool_points if cp.chapter_num > current_chapter - 10]
        active_debts = self.get_active_debts(current_chapter)
        overdue_debts = self.get_overdue_debts(current_chapter)

        return {
            "total_hooks": len(self.hooks),
            "total_cool_points": len(self.cool_points),
            "total_micro_payoffs": len(self.micro_payoffs),
            "recent_hooks_count": len(recent_hooks),
            "recent_cool_points_count": len(recent_cool_points),
            "active_debts": len(active_debts),
            "overdue_debts": len(overdue_debts),
            "total_interest": self.calculate_interest(current_chapter),
        }
