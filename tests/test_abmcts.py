"""Tests for the bounded AB-MCTS strategy search."""
import pytest

from dd2dash0 import abmcts

REWARDS = {
    ("composed", None): 0.8,
    ("composed", "$__interval"): 0.72,
    ("partial_with_warning", None): 0.4,
    ("partial_with_warning", "$__interval"): 0.36,
}


def _search(seed):
    """Search the p95-like space with fixed rewards."""
    return abmcts.search(("composed", "partial_with_warning"), (None, "$__interval"), lambda s, v: REWARDS[s, v], seed=seed)


def test_search_finds_best_and_is_deterministic():
    """The best evaluated candidate wins, and a fixed seed reproduces the trace."""
    first, second = _search(7), _search(7)
    assert (first.strategy, first.variant, first.reward) == ("composed", None, 0.8)
    assert first.trace == second.trace
    assert first.iterations == len(first.trace) == 4  # the space is exhausted before the budget
    assert {step[1] for step in first.trace} == {"GEN", "CONT"}


def test_early_stop_and_budget():
    """A perfect reward stops the search; the budget bounds an endless space."""
    found = abmcts.search(("direct", "manual"), (None,), lambda s, v: 1.0 if s == "direct" else 0.0, seed=1)
    assert found.strategy == "direct" and found.trace[-1][-1] == 1.0
    bounded = abmcts.search(("composed",), tuple(range(100)), lambda s, v: 0.5, seed=3, budget=5)
    assert bounded.iterations == 5


def test_strategies_must_come_from_the_registry():
    """The search never invents a strategy outside the fixed registry."""
    with pytest.raises(ValueError, match="registry"):
        abmcts.search(("llm_rewrite",), (None,), lambda s, v: 1.0)
