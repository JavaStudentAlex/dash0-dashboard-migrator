"""SIFT evidence gate: Stop, Investigate source, Find target support, Trace provenance."""
import math
import re
from dataclasses import dataclass

from dd2dash0.ir import MetricQuery
from dd2dash0.ontology import Concept

PERCENTILE = re.compile(r"p(50|75|90|95|99)")
SPACE_AGGREGATORS = {"avg", "sum", "min", "max", "count"}
SOURCE_MODIFIERS = {"as_count", "as_rate"}
SOURCE_FUNCTIONS = {"top"}
TARGET_FUNCTIONS = {"increase", "rate", "avg_over_time", "min_over_time", "max_over_time", "sum_over_time",
                    "histogram_quantile", "topk", "bottomk", "sum", "avg", "min", "max", "count"}


@dataclass(frozen=True)
class SiftVerdict:
    """Gate result for one compiled candidate."""

    score: float
    status: str
    checks: dict[str, bool]
    warnings: tuple[str, ...]


def source_gap(query: MetricQuery, concept: Concept) -> str | None:
    """Return why the Datadog semantics have no PromQL equivalent, or ``None``."""
    if query.function and query.function not in SOURCE_FUNCTIONS:
        return f"function {query.function}() has no PromQL equivalent"
    if PERCENTILE.fullmatch(query.aggregator):
        if concept.datadog_type != "distribution":
            return f"{query.aggregator} needs a distribution metric"
    elif query.aggregator not in SPACE_AGGREGATORS:
        return f"space aggregator {query.aggregator} is unknown"
    extra = set(query.modifiers) - SOURCE_MODIFIERS
    return f"modifiers {sorted(extra)} have no mapping" if extra else None


def admissible(query: MetricQuery, concept: Concept | None) -> tuple[str, ...]:
    """Return the registry strategies that can express ``query``; empty means unsupported."""
    if concept is None or source_gap(query, concept):
        return ()
    if concept.status != "certified":
        return ("partial_with_warning",)
    if PERCENTILE.fullmatch(query.aggregator):
        return ("composed", "partial_with_warning")
    return ("direct",)


def evaluate(query: MetricQuery, concept: Concept | None, strategy: str, promql: str | None,
             time_aggregation: str | None = None) -> SiftVerdict:
    """Score one compiled candidate in ``[0, 1]``; any failed hard check gives ``unsupported``.

    Approximations multiply their penalties, so a candidate that is both approximate and
    uncertified ranks below either one alone.
    """
    gap = "unknown metric: no ontology concept" if concept is None else source_gap(query, concept)
    used = set(re.findall(r"([a-z_]+)\(", promql or ""))
    checks = {
        "stop": concept is not None and concept.status == "certified",
        "investigate": gap is None,
        "find": promql is not None and used <= TARGET_FUNCTIONS,
        "trace": concept is not None and concept.status in ("certified", "candidate") and bool(concept.provenance),
    }
    if not (checks["investigate"] and checks["find"] and checks["trace"]):
        reasons = [gap] if gap else []
        reasons += [] if checks["find"] else [f"no supported PromQL for strategy {strategy}"]
        reasons += [] if checks["trace"] or concept is None else [f"concept status {concept.status}"]
        return SiftVerdict(0.0, "unsupported", checks, tuple(reasons))
    findings = [
        (not checks["stop"], 0.6, f"uncertified mapping, manual review (status {concept.status}: {concept.rationale})"),
        (bool(PERCENTILE.fullmatch(query.aggregator)), 0.8,
         f"{query.aggregator} via histogram_quantile bucket interpolation approximates the Datadog percentile"),
        (time_aggregation is not None and time_aggregation != query.aggregator, 0.9,
         f"aggregation order: Datadog applies {query.aggregator} across series, then {time_aggregation} over time; "
         "PromQL aggregates over time first"),
        ("rate(" in promql and "[$__interval]" in promql, 0.9,
         "rate() over $__interval can miss samples; $__rate_interval is safer"),
        (strategy == "partial_with_warning", 0.5, "degraded strategy: output needs manual review"),
    ]
    hits = [(factor, warning) for applies, factor, warning in findings if applies]
    return SiftVerdict(math.prod(f for f, _ in hits), "partial" if hits else "migrated", checks,
                       tuple(w for _, w in hits))


def combine(verdicts: list[SiftVerdict]) -> SiftVerdict:
    """Merge per-query verdicts: the weakest score and the worst status win."""
    worst = next(s for s in ("unsupported", "partial", "migrated") if any(v.status == s for v in verdicts))
    checks = {key: all(v.checks[key] for v in verdicts) for key in verdicts[0].checks}
    warnings = tuple(dict.fromkeys(w for v in verdicts for w in v.warnings))
    return SiftVerdict(min(v.score for v in verdicts), worst, checks, warnings)
