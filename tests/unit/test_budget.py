"""Tests for pipeline budget tracking and enforcement.

Tests verify:
- PipelineBudgetTracker initializes with configurable total_limit
- record_usage accumulates token counts immutably (returns new tracker)
- record_usage raises BudgetExceededError when cumulative usage exceeds limit
- remaining_budget returns correct remaining tokens
- usage_summary returns dict with expected structure
- BudgetExceededError stores agent_name, tokens_used, tokens_limit
"""

from __future__ import annotations

import pytest

from ai_hedge_fund.agents.base import (
    AgentUsageRecord,
    BudgetExceededError,
    PipelineBudgetTracker,
)


class TestPipelineBudgetTrackerInit:
    """Test PipelineBudgetTracker initialization."""

    def test_default_total_limit(self) -> None:
        tracker = PipelineBudgetTracker()
        assert tracker.total_limit == 500_000

    def test_custom_total_limit(self) -> None:
        tracker = PipelineBudgetTracker(total_limit=100_000)
        assert tracker.total_limit == 100_000

    def test_initial_records_empty(self) -> None:
        tracker = PipelineBudgetTracker()
        assert tracker.records == ()

    def test_initial_total_used_zero(self) -> None:
        tracker = PipelineBudgetTracker()
        assert tracker.total_used == 0


class TestPipelineBudgetTrackerRecordUsage:
    """Test record_usage accumulation and immutability."""

    def test_returns_new_tracker(self) -> None:
        original = PipelineBudgetTracker()
        updated = original.record_usage("agent1", 100, 50, 150)
        assert updated is not original

    def test_original_unchanged(self) -> None:
        original = PipelineBudgetTracker()
        _updated = original.record_usage("agent1", 100, 50, 150)
        assert original.total_used == 0
        assert original.records == ()

    def test_single_record_total_used(self) -> None:
        tracker = PipelineBudgetTracker()
        updated = tracker.record_usage("agent1", 100, 50, 150)
        assert updated.total_used == 150

    def test_multiple_records_accumulate(self) -> None:
        tracker = PipelineBudgetTracker()
        t1 = tracker.record_usage("agent1", 100, 50, 150)
        t2 = t1.record_usage("agent2", 200, 100, 300)
        assert t2.total_used == 450

    def test_records_tuple_grows(self) -> None:
        tracker = PipelineBudgetTracker()
        t1 = tracker.record_usage("agent1", 100, 50, 150)
        t2 = t1.record_usage("agent2", 200, 100, 300)
        assert len(t2.records) == 2


class TestPipelineBudgetTrackerExceeded:
    """Test budget enforcement raises BudgetExceededError."""

    def test_raises_on_exceed(self) -> None:
        tracker = PipelineBudgetTracker(total_limit=100)
        with pytest.raises(BudgetExceededError):
            tracker.record_usage("big_agent", 500, 200, 700)

    def test_raises_on_cumulative_exceed(self) -> None:
        tracker = PipelineBudgetTracker(total_limit=200)
        t1 = tracker.record_usage("agent1", 50, 25, 100)
        with pytest.raises(BudgetExceededError):
            t1.record_usage("agent2", 80, 40, 150)

    def test_exact_limit_does_not_raise(self) -> None:
        tracker = PipelineBudgetTracker(total_limit=150)
        updated = tracker.record_usage("agent1", 100, 50, 150)
        assert updated.total_used == 150


class TestPipelineBudgetTrackerRemainingBudget:
    """Test remaining_budget calculation."""

    def test_full_budget_remaining(self) -> None:
        tracker = PipelineBudgetTracker(total_limit=500_000)
        assert tracker.remaining_budget == 500_000

    def test_partial_budget_remaining(self) -> None:
        tracker = PipelineBudgetTracker(total_limit=1000)
        updated = tracker.record_usage("agent1", 100, 50, 300)
        assert updated.remaining_budget == 700


class TestPipelineBudgetTrackerUsageSummary:
    """Test usage_summary dict structure."""

    def test_summary_structure(self) -> None:
        tracker = PipelineBudgetTracker(total_limit=10_000)
        t1 = tracker.record_usage("extractor", 100, 50, 150)
        t2 = t1.record_usage("analyzer", 500, 200, 700)
        summary = t2.usage_summary()

        assert summary["total_used"] == 850
        assert summary["total_limit"] == 10_000
        assert summary["remaining"] == 9_150
        assert summary["breakdown_by_agent"] == {"extractor": 150, "analyzer": 700}

    def test_empty_summary(self) -> None:
        tracker = PipelineBudgetTracker()
        summary = tracker.usage_summary()
        assert summary["total_used"] == 0
        assert summary["remaining"] == 500_000
        assert summary["breakdown_by_agent"] == {}


class TestBudgetExceededError:
    """Test BudgetExceededError attributes."""

    def test_stores_agent_name(self) -> None:
        err = BudgetExceededError("my_agent", 1000, 500)
        assert err.agent_name == "my_agent"

    def test_stores_tokens_used(self) -> None:
        err = BudgetExceededError("my_agent", 1000, 500)
        assert err.tokens_used == 1000

    def test_stores_tokens_limit(self) -> None:
        err = BudgetExceededError("my_agent", 1000, 500)
        assert err.tokens_limit == 500

    def test_is_exception(self) -> None:
        err = BudgetExceededError("my_agent", 1000, 500)
        assert isinstance(err, Exception)


class TestAgentUsageRecord:
    """Test AgentUsageRecord is frozen and correct."""

    def test_fields(self) -> None:
        record = AgentUsageRecord("agent1", 100, 50, 150)
        assert record.agent_name == "agent1"
        assert record.input_tokens == 100
        assert record.output_tokens == 50
        assert record.total_tokens == 150

    def test_frozen(self) -> None:
        record = AgentUsageRecord("agent1", 100, 50, 150)
        with pytest.raises(AttributeError):
            record.agent_name = "changed"  # type: ignore[misc]
