"""Compile IR metric queries and formulas to Dash0 PromQL with OTel-native selectors."""
import re

from dd2dash0.ir import Formula, MetricQuery
from dd2dash0.ontology import Concept, Ontology
from dd2dash0.sift import PERCENTILE


def selector(query: MetricQuery, concept: Concept, ontology: Ontology) -> str:
    """Return ``{otel_metric_name="...", label="value", ...}`` for the query filters."""
    matchers = [f'otel_metric_name="{concept.otel_metric_name}"']
    matchers += [f'{ontology.label(key)}="{value}"' for key, value in query.filters]
    return "{" + ", ".join(matchers) + "}"


def _aggregate(operator: str, labels: tuple[str, ...], inner: str) -> str:
    """Wrap ``inner`` in a PromQL aggregation, with ``by`` only when there are labels."""
    return f"{operator} by ({', '.join(labels)}) ({inner})" if labels else f"{operator}({inner})"


def compile_query(query: MetricQuery, concept: Concept | None, ontology: Ontology, strategy: str,
                  window: str | None = None, time_aggregation: str | None = None) -> str | None:
    """Return PromQL for one query, or ``None`` when the strategy cannot express it.

    :param window: monitor window such as ``5m``, or a dashboard range variable; ``None`` picks
        ``$__interval`` for ``increase`` and ``$__rate_interval`` for ``rate``.
    :param time_aggregation: the monitor time aggregation; ``None`` in dashboards.
    """
    if strategy == "manual" or concept is None:
        return None
    sel = selector(query, concept, ontology)
    labels = tuple(ontology.label(group) for group in query.group_by)
    if PERCENTILE.fullmatch(query.aggregator) and concept.instrument == "histogram":
        quantile = int(query.aggregator[1:]) / 100
        inner = f"rate({sel}[{window or '$__rate_interval'}])"
        expression = f"histogram_quantile({quantile:g}, {_aggregate('sum', ('le',) + labels, inner)})"
    elif concept.instrument == "counter":
        function = "rate" if "as_rate" in query.modifiers else "increase"
        default = "$__rate_interval" if function == "rate" else "$__interval"
        expression = _aggregate(query.aggregator, labels, f"{function}({sel}[{window or default}])")
    elif concept.instrument == "gauge":
        inner = f"{time_aggregation}_over_time({sel}[{window}])" if time_aggregation else sel
        expression = _aggregate(query.aggregator, labels, inner)
    else:
        return None
    if query.function == "top":
        operator = "bottomk" if "asc" in query.function_args else "topk"
        expression = f"{operator}({int(query.function_args[0])}, {expression})"
    return expression


def compile_formula(formula: Formula, compiled: dict[str, str]) -> str:
    """Substitute each compiled query, in parentheses, for its name in the formula."""
    if formula.expression.strip() in compiled:
        return compiled[formula.expression.strip()]
    return re.sub(r"\b[a-z]\w*\b", lambda m: f"({compiled[m[0]]})" if m[0] in compiled else m[0], formula.expression)
