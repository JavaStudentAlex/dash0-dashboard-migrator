"""Typed intermediate representation shared by the parser, the gates and the compilers."""
from dataclasses import dataclass


@dataclass(frozen=True)
class MetricQuery:
    """One Datadog metric query, e.g. ``sum:m{env:prod} by {mode}.as_count()``."""

    raw: str
    aggregator: str
    metric: str
    filters: tuple[tuple[str, str], ...] = ()
    group_by: tuple[str, ...] = ()
    modifiers: tuple[str, ...] = ()
    function: str | None = None
    function_args: tuple = ()


@dataclass(frozen=True)
class Formula:
    """Arithmetic expression over named metric queries (``q1 / q2 * 100``)."""

    expression: str
    queries: dict[str, MetricQuery]


@dataclass(frozen=True)
class Widget:
    """One dashboard widget; ``formulas`` is empty for widgets without metric requests."""

    id: int
    type: str
    title: str
    formulas: tuple[Formula, ...]
    text: str | None
    layout: dict | None


@dataclass(frozen=True)
class Monitor:
    """One Datadog metric monitor with its alert window and thresholds."""

    id: int
    name: str
    type: str
    time_aggregation: str
    window: str
    formula: Formula
    comparator: str
    threshold: float
    thresholds: dict
    options: dict
    message: str
    tags: tuple[str, ...]


@dataclass(frozen=True)
class Diagnostic:
    """Migration outcome of one widget or monitor, as listed in the report."""

    asset: str
    item: str
    status: str
    strategy: str
    sift_score: float
    warnings: tuple[str, ...]
