"""End-to-end test of the migration on the REISY fixtures."""
import json
from pathlib import Path

from dd2dash0.pipeline import migrate

FIXTURES = Path(__file__).parent.parent / "fixtures" / "reisy_travel_search"


def _run(seed=7):
    """Migrate the REISY dashboard and all monitors."""
    dashboard = json.loads((FIXTURES / "dashboard.json").read_text())
    monitors = [json.loads(path.read_text()) for path in sorted((FIXTURES / "monitors").glob("*.json"))]
    return migrate(dashboard, monitors, seed=seed)


def test_expected_statuses_and_strategies():
    """Each widget and monitor ends with the status the SIFT rules demand.

    Monitor 3 (avg over 15m of avg across series) is migrated: the same aggregator in
    space and time commutes when all series share one sample interval, which the OTel
    periodic metric reader gives. Monitor 2 is partial: p95 then avg over time is
    not the same as p95 over the window, and histogram_quantile interpolates buckets.
    """
    result = _run()
    items = {item["item"].split(":")[0]: item for item in result.report["items"]}
    status = {key: item["status"] for key, item in items.items()}
    for n in (1, 2, 4, 5, 6, 8):
        assert status[f"widget {n}"] == "migrated", n
    assert (status["widget 3"], items["widget 3"]["strategy"]) == ("partial", "composed")
    assert status["widget 7"] == "partial"
    assert any("uncertified mapping" in w for w in items["widget 7"]["warnings"])
    assert status["widget 9"] == status["widget 10"] == "unsupported"
    assert [status[f"monitor {n}"] for n in (1, 2, 3, 4)] == ["migrated", "partial", "migrated", "unsupported"]
    assert result.report["summary"] == {"migrated": 8, "partial": 3, "unsupported": 3, "total": 14}


def test_outputs_preserve_thresholds_and_windows():
    """Unsupported items stay out of the outputs; thresholds and windows never change."""
    result = _run()
    assert sorted(result.dashboard["spec"]["panels"]) == [f"panel-{n}" for n in range(1, 9)]
    rules = {rule["name"]: rule for rule in result.check_rules}
    assert len(rules) == 3
    error_rate = rules["REISY search error rate high"]
    assert error_rate["thresholds"] == {"failed": 0.05, "degraded": 0.02}
    assert "[5m]" in error_rate["expression"] and error_rate["expression"].endswith(" > $__threshold")
    assert rules["REISY search p95 latency high"]["thresholds"] == {"failed": 8000, "degraded": 5000}
    assert "rate(" in rules["REISY search p95 latency high"]["expression"]
    assert "[10m]" in rules["REISY search p95 latency high"]["expression"]
    assert rules["REISY LLM cost per search over budget"]["thresholds"] == {"failed": 0.1, "degraded": 0.08}
    assert "[15m]" in rules["REISY LLM cost per search over budget"]["expression"]


def test_deterministic_and_markdown():
    """The same seed gives the same result; the markdown report lists every item."""
    first, second = _run(), _run()
    assert first.report == second.report and first.dashboard == second.dashboard
    markdown = first.report_markdown()
    assert "| asset | item | status | strategy | SIFT score | warnings |" in markdown
    assert markdown.count("\n| ") == 15
