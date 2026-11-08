"""Tests for the Perses dashboard builder."""
from dd2dash0.ir import Widget
from dd2dash0.perses import dashboard


def test_panels_layout_and_kinds():
    """Datadog grid positions double to 24 columns; ordered widgets fill two per row."""
    panels = [
        (Widget(1, "timeseries", "A", (), None, {"x": 3, "y": 2, "width": 6, "height": 4}), ["up"]),
        (Widget(2, "note", "About", (), "# hi", None), []),
        (Widget(3, "toplist", "C", (), None, None), ["topk(1, up)"]),
    ]
    result = dashboard("REISY travel-service search", panels)
    assert result["kind"] == "Dashboard"
    assert result["metadata"] == {"name": "reisy-travel-service-search", "project": "default"}
    assert result["spec"]["display"] == {"name": "REISY travel-service search"}
    items = result["spec"]["layouts"][0]["spec"]["items"]
    assert items[0] == {"x": 6, "y": 2, "width": 12, "height": 4, "content": {"$ref": "#/spec/panels/panel-1"}}
    assert [(i["x"], i["y"], i["width"], i["height"]) for i in items[1:]] == [(12, 0, 12, 8), (0, 8, 12, 8)]
    specs = {key: panel["spec"] for key, panel in result["spec"]["panels"].items()}
    assert specs["panel-2"]["plugin"] == {"kind": "Markdown", "spec": {"text": "# hi"}}
    assert "queries" not in specs["panel-2"]
    assert specs["panel-3"]["plugin"]["kind"] == "BarChart"
    assert specs["panel-1"]["queries"] == [
        {"kind": "TimeSeriesQuery", "spec": {"plugin": {"kind": "PrometheusTimeSeriesQuery", "spec": {"query": "up"}}}}
    ]
