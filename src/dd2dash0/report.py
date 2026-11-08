"""Migration report: per-item diagnostics, summary counts and a markdown table."""
from dataclasses import asdict

from dd2dash0.ir import Diagnostic

STATUSES = ("migrated", "partial", "unsupported")


def build_report(diagnostics: list[Diagnostic]) -> dict:
    """Return ``{"summary": counts, "items": diagnostics as dicts}``."""
    summary = {status: sum(d.status == status for d in diagnostics) for status in STATUSES}
    return {"summary": {**summary, "total": len(diagnostics)}, "items": [asdict(d) for d in diagnostics]}


def markdown(report: dict) -> str:
    """Render the report as a markdown table with one row per item."""
    s = report["summary"]
    lines = [f"Migrated {s['migrated']}, partial {s['partial']}, unsupported {s['unsupported']} of {s['total']}.", "",
             "| asset | item | status | strategy | SIFT score | warnings |", "|---|---|---|---|---|---|"]
    for item in report["items"]:
        warnings = "; ".join(item["warnings"]).replace("|", "/")
        lines.append(f"| {item['asset']} | {item['item']} | {item['status']} | {item['strategy']} "
                     f"| {item['sift_score']:.2f} | {warnings} |")
    return "\n".join(lines) + "\n"
