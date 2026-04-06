"""
一致性检查器测试
"""

import pytest
from unittest.mock import Mock, AsyncMock
from src.agents.checkers.consistency_checker import ConsistencyChecker, Issue, CheckResult


class TestConsistencyChecker:
    """一致性检查器测试"""

    @pytest.fixture
    def mock_llm(self):
        """模拟 LLM"""
        llm = Mock()
        llm.generate = AsyncMock(return_value=Mock(text="[]"))
        return llm

    @pytest.fixture
    def mock_state_manager(self):
        """模拟状态管理器"""
        state_manager = Mock()
        mock_state = Mock()
        mock_state.world = {"power_system": "炼气→筑基→金丹→元婴→化神"}
        mock_state.character_states = []
        mock_state.protagonist = {"name": "陈野", "gender": "男"}
        mock_state.entities = {"all": []}
        state_manager.load_state = Mock(return_value=mock_state)
        return state_manager

    @pytest.fixture
    def checker(self, mock_llm, mock_state_manager):
        """创建检查器实例"""
        return ConsistencyChecker(mock_llm, mock_state_manager)

    def test_calculate_score_no_issues(self, checker):
        """测试无问题时的得分"""
        issues = []
        score = checker._calculate_score(issues)
        assert score == 100

    def test_calculate_score_with_critical(self, checker):
        """测试严重问题扣分"""
        issues = [
            Issue(id="CONS-001", severity="critical", category="test", description="test"),
            Issue(id="CONS-002", severity="critical", category="test", description="test"),
        ]
        score = checker._calculate_score(issues)
        assert score == 40  # 100 - 30*2

    def test_calculate_score_with_high(self, checker):
        """测试高优先级问题扣分"""
        issues = [
            Issue(id="CONS-001", severity="high", category="test", description="test"),
        ]
        score = checker._calculate_score(issues)
        assert score == 80  # 100 - 20

    def test_calculate_score_with_medium(self, checker):
        """测试中优先级问题扣分"""
        issues = [
            Issue(id="CONS-001", severity="medium", category="test", description="test"),
            Issue(id="CONS-002", severity="medium", category="test", description="test"),
        ]
        score = checker._calculate_score(issues)
        assert score == 80  # 100 - 10*2

    def test_generate_summary_no_issues(self, checker):
        """测试无问题时的总结"""
        issues = []
        summary = checker._generate_summary(issues)
        assert "未发现矛盾" in summary

    def test_generate_summary_with_issues(self, checker):
        """测试有问题时的总结"""
        issues = [
            Issue(id="CONS-001", severity="high", category="test", description="test"),
            Issue(id="CONS-002", severity="medium", category="test", description="test"),
        ]
        summary = checker._generate_summary(issues)
        assert "2 个问题" in summary
        assert "高优先级: 1 个" in summary
        assert "中优先级: 1 个" in summary

    @pytest.mark.asyncio
    async def test_check_returns_result(self, checker):
        """测试 check 方法返回结果"""
        result = await checker.check(
            chapter_num=1,
            content="测试内容" * 100,
        )
        assert isinstance(result, CheckResult)
        assert result.checker == "consistency"
        assert isinstance(result.score, int)
        assert isinstance(result.summary, str)
