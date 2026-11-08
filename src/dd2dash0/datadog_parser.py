"""Parse Datadog dashboard and monitor exports into the typed IR."""
import re

from dd2dash0.ir import Formula, MetricQuery, Monitor, Widget

_QUERY = r"[a-z0-9_]+:[\w.]+\{[^}]*\}(?:\s+by\s+\{[^}]*\})?(?:\.\w+\([^)]*\))*"
_TOKEN = re.compile(
    rf"(?P<fn>[a-z_]+)\((?P<inner>{_QUERY})(?P<args>(?:\s*,\s*(?:'[^']*'|[\w.]+))*)\s*\)|(?P<plain>{_QUERY})"
)
_PARTS = re.compile(
    r"(?P<agg>[a-z0-9_]+):(?P<metric>[\w.]+)\{(?P<tags>[^}]*)\}(?:\s+by\s+\{(?P<by>[^}]*)\})?(?P<mods>.*)", re.S
)
_MONITOR = re.compile(
    r"(?P<tagg>\w+)\(last_(?P<window>\d+[mhdw])\):(?P<expr>.+?)\s*(?P<cmp>>=|<=|==|!=|>|<)\s*(?P<threshold>-?[\d.]+)",
    re.S,
)
METRIC_WIDGETS = {"timeseries", "query_value", "toplist"}


def _query(token: re.Match) -> MetricQuery:
    """Build a :class:`MetricQuery` from a matched query token."""
    parts = _PARTS.fullmatch(token["inner"] or token["plain"])
    tags = (tag.strip() for tag in parts["tags"].split(","))
    return MetricQuery(
        raw=token[0],
        aggregator=parts["agg"],
        metric=parts["metric"],
        filters=tuple(tag.partition(":")[::2] for tag in tags if tag not in ("", "*")),
        group_by=tuple(g.strip() for g in (parts["by"] or "").split(",") if g.strip()),
        modifiers=tuple(re.findall(r"\.(\w+)\(", parts["mods"])),
        function=token["fn"],
        function_args=tuple(a.strip().strip("'") for a in (token["args"] or "").split(",") if a.strip()),
    )


def parse_query(text: str) -> MetricQuery:
    """Parse one metric query, optionally wrapped in a function such as ``top(...)``.

    :raises ValueError: if the text does not follow the Datadog metric query grammar.
    """
    token = _TOKEN.fullmatch(text.strip())
    if token is None:
        raise ValueError(f"not a Datadog metric query: {text!r}")
    return _query(token)


def parse_formula(expression: str) -> Formula:
    """Name every metric query in an arithmetic expression ``q1``, ``q2``, ... in order.

    :raises ValueError: if the expression holds no metric query.
    """
    queries = {}

    def name(token: re.Match) -> str:
        """Store the query and return its name for the rewritten expression."""
        key = f"q{len(queries) + 1}"
        queries[key] = _query(token)
        return key

    rewritten = _TOKEN.sub(name, expression.strip())
    if not queries:
        raise ValueError(f"no Datadog metric query in {expression!r}")
    return Formula(rewritten, queries)


def _formulas(request: dict) -> list[Formula]:
    """Read a legacy ``q`` request or a ``queries`` + ``formulas`` request."""
    if "q" in request:
        return [parse_formula(request["q"])]
    queries = {q["name"]: parse_query(q["query"]) for q in request["queries"]}
    return [Formula(f["formula"], queries) for f in request["formulas"]]


def parse_dashboard(data: dict) -> tuple[str, list[Widget]]:
    """Return the dashboard title and its widgets in export order.

    Widget types without metric requests (note, log_stream, unknown) are kept with no formulas,
    so later stages can report them instead of failing here.
    """
    widgets = []
    for raw in data["widgets"]:
        definition = raw["definition"]
        formulas = ()
        if definition["type"] in METRIC_WIDGETS:
            formulas = tuple(f for request in definition.get("requests", []) for f in _formulas(request))
        widgets.append(Widget(raw["id"], definition["type"], definition.get("title", ""), formulas,
                              definition.get("content"), raw.get("layout")))
    return data["title"], widgets


def parse_monitor(data: dict) -> Monitor:
    """Parse a metric monitor ``TIMEAGG(last_N):EXPR COMPARATOR THRESHOLD``.

    :raises ValueError: if the query does not follow the metric monitor grammar.
    """
    match = _MONITOR.fullmatch(data["query"].strip())
    if match is None:
        raise ValueError(f"monitor {data['id']}: unsupported query grammar {data['query']!r}")
    options = data.get("options", {})
    return Monitor(
        id=data["id"],
        name=data["name"],
        type=data["type"],
        time_aggregation=match["tagg"],
        window=match["window"],
        formula=parse_formula(match["expr"]),
        comparator=match["cmp"],
        threshold=float(match["threshold"]),
        thresholds=options.get("thresholds", {}),
        options=options,
        message=data.get("message", ""),
        tags=tuple(data.get("tags", ())),
    )
