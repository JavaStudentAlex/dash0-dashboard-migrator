"""Tests for the PromQL compiler."""
from dd2dash0.datadog_parser import parse_formula, parse_query
from dd2dash0.ontology import Ontology
from dd2dash0.promql import compile_formula, compile_query

ONTOLOGY = Ontology()
REQUESTS = '{otel_metric_name="reisy.search.requests", service_name="travel-service"}'
COST = '{otel_metric_name="reisy.search.llm_cost_usd", service_name="travel-service"}'


def _compile(text, strategy="direct", window=None, time_aggregation=None):
    """Parse and compile one query against the seed ontology."""
    query = parse_query(text)
    return compile_query(query, ONTOLOGY.resolve(query.metric), ONTOLOGY, strategy, window, time_aggregation)


def test_counter_uses_increase_or_rate():
    """``as_count`` maps to ``increase``, ``as_rate`` to ``rate``; monitors use their window."""
    assert _compile("sum:reisy.search.requests{env:prod,service:travel-service} by {mode}.as_count()") == (
        'sum by (mode) (increase({otel_metric_name="reisy.search.requests", '
        'deployment_environment_name="prod", service_name="travel-service"}[$__interval]))'
    )
    assert _compile("sum:reisy.search.requests{service:travel-service}.as_count()", window="5m") == (
        f"sum(increase({REQUESTS}[5m]))"
    )
    assert _compile("sum:reisy.search.requests{service:travel-service}.as_rate()") == (
        f"sum(rate({REQUESTS}[$__rate_interval]))"
    )


def test_gauge_and_percentile():
    """Gauges aggregate directly (or over the monitor window); percentiles use histogram_quantile."""
    assert _compile("avg:reisy.search.llm_cost_usd{service:travel-service} by {model}") == f"avg by (model) ({COST})"
    assert _compile("avg:reisy.search.llm_cost_usd{service:travel-service}", window="15m", time_aggregation="avg") == (
        f"avg(avg_over_time({COST}[15m]))"
    )
    assert _compile("p95:reisy.search.latency{service:travel-service} by {mode}", "composed") == (
        'histogram_quantile(0.95, sum by (le, mode) (rate({otel_metric_name="reisy.search.latency", '
        'service_name="travel-service"}[$__rate_interval])))'
    )


def test_top_and_formula_substitution():
    """``top`` maps to ``topk``; formulas substitute compiled queries in parentheses."""
    top = "top(sum:reisy.search.provider.calls{service:travel-service} by {provider}.as_count(), 10, 'sum', 'desc')"
    assert _compile(top).startswith("topk(10, sum by (provider) (increase(")
    formula = parse_formula("sum:reisy.search.errors{*}.as_count() / sum:reisy.search.requests{*}.as_count()")
    assert compile_formula(formula, {"q1": "A", "q2": "B"}) == "(A) / (B)"
    assert compile_formula(parse_formula("sum:reisy.search.requests{*}.as_count()"), {"q1": "A"}) == "A"
