"""Client for the Datadog v1 dashboard and monitor read API."""

import os

import httpx

from dd2dash0.clients import checked_json


class DatadogClient:
    """Read dashboards and monitors from one Datadog site.

    :param api_key: Datadog API key; sent as ``DD-API-KEY``.
    :param app_key: Datadog application key; sent as ``DD-APPLICATION-KEY``.
    :param site: Datadog site, for example ``datadoghq.eu``.
    :param transport: Optional httpx transport; tests pass a mock here.
    """

    def __init__(
        self, api_key: str, app_key: str, site: str = "datadoghq.com", transport: httpx.BaseTransport | None = None
    ):
        self._http = httpx.Client(
            base_url=f"https://api.{site}",
            headers={"DD-API-KEY": api_key, "DD-APPLICATION-KEY": app_key},
            transport=transport,
            timeout=30,
        )

    @classmethod
    def from_env(cls) -> "DatadogClient":
        """Build a client from ``DD_API_KEY``, ``DD_APP_KEY`` and ``DD_SITE`` (optional).

        :raises KeyError: If a key variable is not set.
        """
        return cls(os.environ["DD_API_KEY"], os.environ["DD_APP_KEY"], os.environ.get("DD_SITE", "datadoghq.com"))

    def get_dashboard(self, dashboard_id: str) -> dict:
        """Return a dashboard in Datadog export format.

        :param dashboard_id: Datadog dashboard id, for example ``abc-def-ghi``.
        """
        return checked_json(self._http.get(f"/api/v1/dashboard/{dashboard_id}"))

    def get_monitor(self, monitor_id: int | str) -> dict:
        """Return a monitor in Datadog export format.

        :param monitor_id: Numeric Datadog monitor id.
        """
        return checked_json(self._http.get(f"/api/v1/monitor/{monitor_id}"))
