"""Build a Perses dashboard, the Dash0 dashboard format, from widgets and their PromQL."""
import re

from dd2dash0.ir import Widget

PANEL_KINDS = {"timeseries": "TimeSeriesChart", "query_value": "StatChart", "toplist": "BarChart", "note": "Markdown"}


def _panel(widget: Widget, queries: list[str]) -> dict:
    """Return one Perses panel; Markdown panels carry the note text and no queries."""
    kind = PANEL_KINDS[widget.type]
    spec = {"display": {"name": widget.title},
            "plugin": {"kind": kind, "spec": {"text": widget.text} if kind == "Markdown" else {}}}
    if queries:
        spec["queries"] = [{"kind": "TimeSeriesQuery",
                            "spec": {"plugin": {"kind": "PrometheusTimeSeriesQuery", "spec": {"query": q}}}}
                           for q in queries]
    return {"kind": "Panel", "spec": spec}


def dashboard(title: str, panels: list[tuple[Widget, list[str]]]) -> dict:
    """Return the Perses dashboard for the migrated widgets.

    Datadog uses a 12-column grid and Perses a 24-column grid, so x and width double.
    Widgets without a position (ordered layout) fill two panels per row.
    """
    items = []
    for index, (widget, _) in enumerate(panels):
        layout = widget.layout
        if layout:
            position = {"x": layout["x"] * 2, "y": layout["y"], "width": layout["width"] * 2, "height": layout["height"]}
        else:
            position = {"x": index % 2 * 12, "y": index // 2 * 8, "width": 12, "height": 8}
        items.append({**position, "content": {"$ref": f"#/spec/panels/panel-{widget.id}"}})
    return {
        "kind": "Dashboard",
        "metadata": {"name": re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-"), "project": "default"},
        "spec": {
            "display": {"name": title},
            "duration": "1h",
            "variables": [],
            "panels": {f"panel-{widget.id}": _panel(widget, queries) for widget, queries in panels},
            "layouts": [{"kind": "Grid", "spec": {"items": items}}],
        },
    }
