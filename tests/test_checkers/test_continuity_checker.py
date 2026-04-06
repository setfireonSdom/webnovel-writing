"""
连贯性检查器测试
"""

import pytest
from unittest.mock import Mock, AsyncMock
from src.agents.checkers.continuity_checker import ContinuityChecker, Issue, CheckResult


class TestContinuityChecker:
    """连贯性检查器测试"""

    @pytest.fixture
    def mock_llm(self):
        llm = Mock()
        llm.generate = AsyncMock(return_value=Mock(text="[]"))
        return llm

    @pytest.fixture
    def mock_state_manager(self):
        state_manager = Mock()
        return state_manager

    @pytest.fixture
    def checker(self, mock_llm, mock_state_manager):
        return ContinuityChecker(mock_llm, mock_state_manager)

    def test_calculate_score_no_issues(self, checker):
        issues = []
        score = checker._calculate_score(issues)
        assert score == 100

    def test_calculate_score_mixed(self, checker):
        issues = [
            Issue(id="CONT-001", severity="high", category="test", description="test"),
            Issue(id="CONT-002", severity="medium", category="test", description="test"),
            Issue(id="CONT-003", severity="low", category="test", description="test"),
        ]
        score = checker._calculate_score(issues)
        assert score == 65  # 100 - 20 - 10 - 5

    def test_generate_summary_no_issues(self, checker):
        summary = checker._generate_summary([])
        assert "叙事流畅" in summary

    @pytest.mark.asyncio
    async def test_check_returns_result(self, checker):
        result = await checker.check(
            chapter_num=1,
            content="测试内容" * 100,
            previous_summary="前情提要",
        )
        assert isinstance(result, CheckResult)
        assert result.checker == "continuity"
