"""Tests for the Datadog dashboard and monitor parser."""
import json
from pathlib import Path

from dd2dash0.datadog_parser import parse_dashboard, parse_formula, parse_monitor

FIXTURES = Path(__file__).parent.parent / "fixtures" / "reisy_travel_search"


def test_legacy_query_with_group_by_and_modifier():
    """A legacy ``q`` string becomes one named query with filters, groups and modifiers."""
    formula = parse_formula("sum:reisy.search.requests{env:prod,service:travel-service} by {mode}.as_count()")
    query = formula.queries["q1"]
    assert formula.expression == "q1"
    assert (query.aggregator, query.metric, query.function) == ("sum", "reisy.search.requests", None)
    assert query.filters == (("env", "prod"), ("service", "travel-service"))
    assert (query.group_by, query.modifiers) == (("mode",), ("as_count",))


def test_function_wrapper_keeps_arguments():
    """``top(...)`` wraps the query and keeps its arguments; ``*`` means no filter."""
    top = parse_formula("top(sum:reisy.search.provider.calls{*} by {provider}.as_count(), 10, 'sum', 'desc')")
    query = top.queries["q1"]
    assert (query.function, query.function_args, query.filters) == ("top", ("10", "sum", "desc"), ())


def test_monitor_arithmetic_query():
    """A monitor query keeps time aggregation, window, comparator and threshold exactly."""
    monitor = parse_monitor(json.loads((FIXTURES / "monitors" / "m1_error_rate.json").read_text()))
    assert (monitor.time_aggregation, monitor.window, monitor.comparator, monitor.threshold) == ("sum", "5m", ">", 0.05)
    assert monitor.formula.expression == "q1 / q2"
    assert [q.metric for q in monitor.formula.queries.values()] == ["reisy.search.errors", "reisy.search.requests"]


def test_dashboard_formula_form_and_unknown_widget_types():
    """Formula-form requests are parsed; widget types without metric requests flow through empty."""
    title, widgets = parse_dashboard(json.loads((FIXTURES / "dashboard.json").read_text()))
    by_id = {widget.id: widget for widget in widgets}
    assert title == "REISY travel-service search"
    assert by_id[2].formulas[0].expression == "q1 / q2 * 100"
    assert by_id[9].type == "log_stream" and by_id[9].formulas == ()
    assert by_id[8].text.startswith("# REISY")
