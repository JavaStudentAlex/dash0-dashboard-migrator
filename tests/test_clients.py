"""Tests for the Dash0 and Datadog HTTP clients against :class:`httpx.MockTransport`."""

import json

import httpx
import pytest

from dd2dash0.clients import APIError
from dd2dash0.clients.dash0 import Dash0Client
from dd2dash0.clients.datadog import DatadogClient

TOKEN = "dash0-secret-token"


def _transport(seen: list[httpx.Request], status: int = 200, body: object = None) -> httpx.MockTransport:
    """Return a transport that records each request and answers with one fixed response.

    :param seen: List that receives every request.
    :param status: HTTP status of the response.
    :param body: JSON body of the response; ``None`` echoes the request body.
    """

    def handle(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        payload = body if body is not None else json.loads(request.content or b"{}")
        return httpx.Response(status, json=payload)

    return httpx.MockTransport(handle)


def test_dash0_import_dashboard_posts_to_import_endpoint_with_dataset_and_bearer():
    """The dashboard goes as JSON to the import endpoint of the chosen dataset."""
    seen: list[httpx.Request] = []
    client = Dash0Client("https://dash0.test", TOKEN, dataset="prod", transport=_transport(seen))
    dashboard = {"kind": "Dashboard", "metadata": {"name": "search"}, "spec": {}}

    assert client.import_dashboard(dashboard) == dashboard
    (request,) = seen
    assert request.method == "POST"
    assert request.url.path == "/api/import/dashboard"
    assert request.url.params["dataset"] == "prod"
    assert request.headers["Authorization"] == f"Bearer {TOKEN}"
    assert json.loads(request.content) == dashboard


def test_dash0_import_check_rule_posts_to_import_endpoint():
    """The check rule goes as JSON to the check-rule import endpoint."""
    seen: list[httpx.Request] = []
    client = Dash0Client("https://dash0.test", TOKEN, transport=_transport(seen))
    rule = {"name": "High search latency", "expression": "up == 0"}

    assert client.import_check_rule(rule) == rule
    (request,) = seen
    assert (request.method, request.url.path) == ("POST", "/api/import/check-rule")
    assert request.url.params["dataset"] == "default"


def test_dash0_read_back_uses_get_endpoints_by_id():
    """Read-back calls the dashboard and check-rule GET endpoints with the dataset."""
    seen: list[httpx.Request] = []
    client = Dash0Client("https://dash0.test", TOKEN, dataset="prod", transport=_transport(seen, body={"ok": 1}))

    client.get_dashboard("d-1")
    client.get_check_rule("r-1")

    assert [(r.method, r.url.path, r.url.params["dataset"]) for r in seen] == [
        ("GET", "/api/dashboards/d-1", "prod"),
        ("GET", "/api/alerting/check-rules/r-1", "prod"),
    ]


def test_dash0_error_carries_status_and_body_but_not_token():
    """A non-2xx answer raises with status and body, and the token stays secret."""
    client = Dash0Client(
        "https://dash0.test", TOKEN, transport=_transport([], status=400, body={"error": {"message": "bad spec"}})
    )

    with pytest.raises(APIError) as caught:
        client.import_dashboard({"kind": "Dashboard"})

    message = str(caught.value)
    assert "400" in message and "bad spec" in message
    assert TOKEN not in message


def test_datadog_get_dashboard_and_monitor_use_site_and_key_headers():
    """Both reads go to the v1 API of the site with the API and application keys."""
    seen: list[httpx.Request] = []
    client = DatadogClient("api-key", "app-key", site="datadoghq.eu", transport=_transport(seen, body={"id": "x"}))

    client.get_dashboard("abc-def-ghi")
    client.get_monitor(42)

    assert [str(r.url) for r in seen] == [
        "https://api.datadoghq.eu/api/v1/dashboard/abc-def-ghi",
        "https://api.datadoghq.eu/api/v1/monitor/42",
    ]
    assert all(r.headers["DD-API-KEY"] == "api-key" for r in seen)
    assert all(r.headers["DD-APPLICATION-KEY"] == "app-key" for r in seen)


def test_datadog_error_carries_status_and_body_but_not_keys():
    """A Datadog error raises with status and body, and both keys stay secret."""
    client = DatadogClient("api-key", "app-key", transport=_transport([], status=403, body={"errors": ["Forbidden"]}))

    with pytest.raises(APIError) as caught:
        client.get_monitor(7)

    message = str(caught.value)
    assert "403" in message and "Forbidden" in message
    assert "api-key" not in message and "app-key" not in message
