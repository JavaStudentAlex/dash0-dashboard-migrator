"""Translate a parsed Datadog monitor and its PromQL into a Dash0 check rule."""
from dd2dash0.ir import Monitor

UNMAPPED_OPTIONS = ("notify_no_data", "renotify_interval", "evaluation_delay", "require_full_window")


def check_rule(monitor: Monitor, promql: str) -> tuple[dict, tuple[str, ...]]:
    """Return the check rule and warnings for monitor options that have no mapping.

    The comparator and thresholds are kept as they are; the window is already inside ``promql``.
    """
    thresholds = {"failed": monitor.thresholds.get("critical", monitor.threshold)}
    if "warning" in monitor.thresholds:
        thresholds["degraded"] = monitor.thresholds["warning"]
    words = [word for word in monitor.message.split() if not word.startswith("@")]
    rule = {
        "name": monitor.name,
        "expression": f"{promql} {monitor.comparator} $__threshold",
        "thresholds": thresholds,
        "interval": "1m",
        "for": "0s",
        "keepFiringFor": "0s",
        "labels": dict(tag.partition(":")[::2] for tag in monitor.tags),
        "annotations": {"summary": monitor.name, "description": " ".join(words)},
        "enabled": True,
    }
    warnings = tuple(f"option {key}={monitor.options[key]!r} has no Dash0 check-rule mapping"
                     for key in UNMAPPED_OPTIONS if key in monitor.options)
    return rule, warnings
