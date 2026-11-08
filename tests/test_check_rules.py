"""Tests for the Dash0 check rule builder."""
import dataclasses
import json
from pathlib import Path

from dd2dash0.check_rules import check_rule
from dd2dash0.datadog_parser import parse_monitor

FIXTURES = Path(__file__).parent.parent / "fixtures" / "reisy_travel_search"


def test_rule_keeps_threshold_comparator_and_labels():
    """Thresholds, comparator and tags carry over; handles leave the description; options warn."""
    monitor = parse_monitor(json.loads((FIXTURES / "monitors" / "m1_error_rate.json").read_text()))
    rule, warnings = check_rule(monitor, "X")
    assert rule["expression"] == "X > $__threshold"
    assert rule["thresholds"] == {"failed": 0.05, "degraded": 0.02}
    assert rule["labels"] == {"team": "reisy", "service": "travel-service"}
    assert rule["annotations"] == {"summary": "REISY search error rate high",
                                   "description": "Search error rate above 5% for 5 minutes."}
    assert (rule["interval"], rule["for"], rule["keepFiringFor"], rule["enabled"]) == ("1m", "0s", "0s", True)
    assert warnings == ("option notify_no_data=False has no Dash0 check-rule mapping",)
    rule, _ = check_rule(dataclasses.replace(monitor, thresholds={"critical": 0.05}), "X")
    assert rule["thresholds"] == {"failed": 0.05}
