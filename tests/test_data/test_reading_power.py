"""
追读力系统测试
"""

import pytest
import tempfile
from pathlib import Path
from src.data.reading_power import (
    ReadingPowerTracker,
    Hook,
    CoolPoint,
    MicroPayoff,
    Debt,
)


class TestReadingPowerTracker:
    """追读力追踪器测试"""

    @pytest.fixture
    def tracker(self):
        """创建临时目录的追踪器"""
        with tempfile.TemporaryDirectory() as tmpdir:
            tracker = ReadingPowerTracker(Path(tmpdir))
            yield tracker

    def test_init_empty(self, tracker):
        """测试初始化空数据"""
        assert len(tracker.hooks) == 0
        assert len(tracker.cool_points) == 0
        assert len(tracker.debts) == 0

    def test_add_hook(self, tracker):
        """测试添加钩子"""
        hook = Hook(
            type="悬念",
            strength=80,
            description="主角能否突破境界？",
            chapter_num=1,
            anchor="主角的突破结果",
        )
        tracker.add_hook(hook)
        assert len(tracker.hooks) == 1
        assert tracker.hooks[0].type == "悬念"

    def test_add_cool_point(self, tracker):
        """测试添加爽点"""
        cp = CoolPoint(
            type="装逼打脸",
            intensity="high",
            description="主角击败挑衅者",
            chapter_num=1,
        )
        tracker.add_cool_point(cp)
        assert len(tracker.cool_points) == 1

    def test_add_debt(self, tracker):
        """测试添加债务"""
        debt = Debt(
            description="承诺第5章突破境界",
            chapter_created=1,
            chapter_due=5,
        )
        tracker.add_debt(debt)
        assert len(tracker.debts) == 1

    def test_debt_interest_calculation(self, tracker):
        """测试债务利息计算"""
        debt = Debt(
            description="承诺突破境界",
            chapter_created=1,
            chapter_due=5,
            interest_rate=0.1,
        )
        tracker.add_debt(debt)

        # 第 10 章时，超期 5 章
        interest = tracker.calculate_interest(10)
        assert interest == pytest.approx(0.5)  # 5 * 0.1

    def test_active_debts(self, tracker):
        """测试活跃债务"""
        debt1 = Debt(
            description="债务1",
            chapter_created=1,
            chapter_due=5,
        )
        debt2 = Debt(
            description="债务2",
            chapter_created=2,
            chapter_due=10,
        )
        tracker.add_debt(debt1)
        tracker.add_debt(debt2)

        # 第 8 章时，只有债务1到期
        active = tracker.get_active_debts(8)
        assert len(active) == 1
        assert active[0].description == "债务1"

    def test_overdue_debts(self, tracker):
        """测试超期债务"""
        debt = Debt(
            description="超期债务",
            chapter_created=1,
            chapter_due=5,
        )
        tracker.add_debt(debt)

        # 第 15 章时，超过 5 章宽限期
        overdue = tracker.get_overdue_debts(15)
        assert len(overdue) == 1

    def test_micro_payoff_clears_debt(self, tracker):
        """测试微兑现清偿债务"""
        debt = Debt(
            description="承诺A",
            chapter_created=1,
            chapter_due=5,
        )
        tracker.add_debt(debt)

        payoff = MicroPayoff(
            description="兑现承诺A",
            chapter_num=5,
            debt_cleared="承诺A",
        )
        tracker.add_micro_payoff(payoff)

        assert tracker.debts[0].is_paid is True
        assert tracker.debts[0].chapter_paid == 5

    def test_evaluate_chapter(self, tracker):
        """测试章节评估"""
        # 添加一些数据
        tracker.add_debt(Debt(
            description="未兑现承诺",
            chapter_created=1,
            chapter_due=3,
        ))

        result = tracker.evaluate_chapter(
            chapter_num=5,
            hook_strength=70,
            cool_point_count=2,
        )

        assert result["chapter_num"] == 5
        assert result["hook_score"] == 70
        assert result["cool_point_score"] == 40  # 2 * 20
        assert result["active_debts"] >= 1
        assert result["final_score"] >= 0

    def test_save_and_load(self, tracker, tmp_path):
        """测试保存和加载"""
        tracker.add_hook(Hook(
            type="悬念",
            strength=80,
            description="测试",
            chapter_num=1,
        ))

        # 数据会自动保存
        # 创建新实例加载数据
        tracker2 = ReadingPowerTracker(tracker.project_root)
        assert len(tracker2.hooks) == 1
        assert tracker2.hooks[0].type == "悬念"

    def test_get_summary(self, tracker):
        """测试获取总结"""
        tracker.add_hook(Hook(
            type="悬念",
            strength=80,
            description="测试",
            chapter_num=15,
        ))
        tracker.add_cool_point(CoolPoint(
            type="装逼打脸",
            intensity="high",
            description="测试",
            chapter_num=15,
        ))

        summary = tracker.get_summary(20)
        assert summary["total_hooks"] == 1
        assert summary["total_cool_points"] == 1
        assert "recent_hooks_count" in summary  # 修复：使用正确的键名
