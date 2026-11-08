"""Tests for the ``dd2dash0`` command line with a fake pipeline and mocked HTTP."""

import json
import sys
import types

import httpx

from dd2dash0.cli import main
from dd2dash0.clients.dash0 import Dash0Client
from dd2dash0.clients.datadog import DatadogClient

DASHBOARD = {"kind": "Dashboard", "metadata": {"name": "search-overview"}, "spec": {"panels": {}}}
RULES = [{"name": "High search latency", "expression": "a > 1"}, {"name": "Search errors", "expression": "b > 0"}]


def _write(path, payload):
    """Write ``payload`` as JSON to ``path``, creating parent directories."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload))


def test_migrate_writes_dashboard_rules_and_report(tmp_path, monkeypatch, capsys):
    """migrate passes the inputs and seed to the pipeline and writes every artifact."""
    calls = {}

    def migrate(dashboard, monitors, *, seed=7):
        calls.update(dashboard=dashboard, monitors=monitors, seed=seed)
        return types.SimpleNamespace(
            dashboard=DASHBOARD,
            check_rules=RULES,
            report={"summary": "2 monitors -> 2 check rules"},
            report_markdown=lambda: "# Report\n",
        )

    monkeypatch.setitem(sys.modules, "dd2dash0.pipeline", types.SimpleNamespace(migrate=migrate))
    _write(tmp_path / "dd" / "dashboard.json", {"title": "Search"})
    _write(tmp_path / "dd" / "monitors" / "2.json", {"id": 2})
    _write(tmp_path / "dd" / "monitors" / "1.json", {"id": 1})
    out = tmp_path / "out"

    code = main(["migrate", "--dashboard", str(tmp_path / "dd" / "dashboard.json"),
                 "--monitors", str(tmp_path / "dd" / "monitors"), "--out", str(out), "--seed", "3"])

    assert code == 0
    assert calls == {"dashboard": {"title": "Search"}, "monitors": [{"id": 1}, {"id": 2}], "seed": 3}
    assert json.loads((out / "dashboard.perses.json").read_text()) == DASHBOARD
    assert sorted(p.name for p in (out / "check_rules").iterdir()) == ["01_high-search-latency.json", "02_search-errors.json"]
    assert json.loads((out / "report.json").read_text()) == {"summary": "2 monitors -> 2 check rules"}
    assert (out / "report.md").read_text() == "# Report\n"
    assert "2 monitors -> 2 check rules" in capsys.readouterr().out


def _migrated(out):
    """Create the files that ``migrate`` writes, with the module constants as content."""
    _write(out / "dashboard.perses.json", DASHBOARD)
    for n, rule in enumerate(RULES, 1):
        _write(out / "check_rules" / f"{n:02d}_rule.json", rule)


def test_import_dry_run_prints_targets_without_network(tmp_path, capsys, monkeypatch):
    """--dry-run never builds a client and prints one target URL per asset."""
    monkeypatch.setenv("DASH0_API_URL", "https://dash0.test")
    _migrated(tmp_path)

    def no_client(dataset):
        raise AssertionError("dry run must not build a client")

    assert main(["import", "--out", str(tmp_path), "--dataset", "prod", "--dry-run"], dash0_factory=no_client) == 0
    lines = capsys.readouterr().out.splitlines()
    assert lines == [
        "dashboard\tsearch-overview\tPOST https://dash0.test/api/import/dashboard?dataset=prod",
        "check-rule\tHigh search latency\tPOST https://dash0.test/api/import/check-rule?dataset=prod",
        "check-rule\tSearch errors\tPOST https://dash0.test/api/import/check-rule?dataset=prod",
    ]


def test_import_imports_every_asset_and_reports_read_back(tmp_path, capsys):
    """Each asset is imported and read back; a failed read-back gives exit code 1."""
    _migrated(tmp_path)
    stored = {}

    def handle(request: httpx.Request) -> httpx.Response:
        if request.method == "POST" and request.url.path == "/api/import/dashboard":
            body = json.loads(request.content)
            body["metadata"]["dash0Extensions"] = {"id": "d-1"}
            stored["/api/dashboards/d-1"] = body
            return httpx.Response(200, json=body)
        if request.method == "POST" and request.url.path == "/api/import/check-rule":
            body = {**json.loads(request.content), "id": f"r-{len(stored)}"}
            if body["name"] == "High search latency":
                stored[f"/api/alerting/check-rules/{body['id']}"] = body
            return httpx.Response(200, json=body)
        if request.url.path in stored:
            return httpx.Response(200, json=stored[request.url.path])
        return httpx.Response(404, json={"error": {"message": "not found"}})

    def factory(dataset):
        return Dash0Client("https://dash0.test", "tok", dataset, transport=httpx.MockTransport(handle))

    assert main(["import", "--out", str(tmp_path)], dash0_factory=factory) == 1
    lines = capsys.readouterr().out.splitlines()
    assert lines[:2] == ["dashboard\tsearch-overview\td-1\tread-back ok", "check-rule\tHigh search latency\tr-1\tread-back ok"]
    assert lines[2].startswith("check-rule\tSearch errors\tr-2\tread-back failed: GET")
    assert "404" in lines[2]


def test_fetch_datadog_saves_dashboard_and_monitors(tmp_path):
    """fetch-datadog stores the API answers unchanged as export files."""

    def handle(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"path": request.url.path})

    def factory():
        return DatadogClient("k", "a", transport=httpx.MockTransport(handle))

    code = main(["fetch-datadog", "--dashboard-id", "abc-def", "--monitor-ids", "1,2", "--out", str(tmp_path)],
                datadog_factory=factory)

    assert code == 0
    assert json.loads((tmp_path / "dashboard.json").read_text()) == {"path": "/api/v1/dashboard/abc-def"}
    assert json.loads((tmp_path / "monitors" / "2.json").read_text()) == {"path": "/api/v1/monitor/2"}
