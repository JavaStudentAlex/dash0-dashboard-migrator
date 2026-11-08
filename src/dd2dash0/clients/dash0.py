"""Client for the Dash0 import and read-back API.

Paths, the ``dataset`` query parameter, the body schemas and the id fields
follow the public OpenAPI document
https://www.dash0.com/docs/api-reference/openapi.json (generated 2026-11-06).
"""

import os

import httpx

from dd2dash0.clients import checked_json

DEFAULT_API_URL = "https://api.europe-west4.gcp.dash0.com"
IMPORT_DASHBOARD_PATH = "/api/import/dashboard"
IMPORT_CHECK_RULE_PATH = "/api/import/check-rule"


def dashboard_id(dashboard: dict) -> str:
    """Return the Dash0 id of a stored dashboard (``metadata.dash0Extensions.id``).

    :param dashboard: A ``DashboardDefinition`` as returned by Dash0.
    """
    return dashboard["metadata"]["dash0Extensions"]["id"]


def check_rule_id(rule: dict) -> str:
    """Return the Dash0 id of a stored check rule (top-level ``id``).

    :param rule: A ``PrometheusAlertRule`` as returned by Dash0.
    """
    return rule["id"]


class Dash0Client:
    """Import dashboards and check rules into one Dash0 dataset and read them back.

    :param base_url: API root, for example ``https://api.europe-west4.gcp.dash0.com``.
    :param auth_token: Dash0 auth token; sent only in the ``Authorization`` header.
    :param dataset: Target dataset; sent as the ``dataset`` query parameter on every call.
    :param transport: Optional httpx transport; tests pass a mock here.
    """

    def __init__(
        self, base_url: str, auth_token: str, dataset: str = "default", transport: httpx.BaseTransport | None = None
    ):
        self._http = httpx.Client(
            base_url=base_url,
            headers={"Authorization": f"Bearer {auth_token}"},
            params={"dataset": dataset},
            transport=transport,
            timeout=30,
        )

    @classmethod
    def from_env(cls, dataset: str = "default") -> "Dash0Client":
        """Build a client from ``DASH0_API_URL`` (optional) and ``DASH0_AUTH_TOKEN``.

        :param dataset: Target dataset.
        :raises KeyError: If ``DASH0_AUTH_TOKEN`` is not set.
        """
        return cls(os.environ.get("DASH0_API_URL", DEFAULT_API_URL), os.environ["DASH0_AUTH_TOKEN"], dataset)

    def import_dashboard(self, dashboard: dict) -> dict:
        """Import a ``DashboardDefinition`` (Perses spec); without an id Dash0 creates a new one.

        :param dashboard: Dict with ``kind``, ``metadata`` and ``spec``.
        :returns: The stored dashboard; see :func:`dashboard_id`.
        """
        return checked_json(self._http.post(IMPORT_DASHBOARD_PATH, json=dashboard))

    def import_check_rule(self, rule: dict) -> dict:
        """Import a ``PrometheusAlertRule``; without an id Dash0 creates a new one.

        :param rule: Dict with at least ``name`` and ``expression``.
        :returns: The stored check rule; see :func:`check_rule_id`.
        """
        return checked_json(self._http.post(IMPORT_CHECK_RULE_PATH, json=rule))

    def get_dashboard(self, dashboard_id: str) -> dict:
        """Read a dashboard back by id.

        :param dashboard_id: Id from :func:`dashboard_id`.
        """
        return checked_json(self._http.get(f"/api/dashboards/{dashboard_id}"))

    def get_check_rule(self, rule_id: str) -> dict:
        """Read a check rule back by id.

        :param rule_id: Id from :func:`check_rule_id`.
        """
        return checked_json(self._http.get(f"/api/alerting/check-rules/{rule_id}"))

    def find_id(self, collection: str, name: str) -> str:
        """Return the id of the asset named ``name`` from a list endpoint.

        Live Dash0 (checked 2026-11-08) answers a dashboard import and a dashboard GET without
        any id; only ``GET /api/dashboards`` lists ``id`` and ``name``.

        :param collection: ``"dashboards"`` or ``"alerting/check-rules"``.
        :param name: Asset name as imported.
        :raises LookupError: If no listed asset has that name.
        """
        listed = checked_json(self._http.get(f"/api/{collection}"))
        matches = [a["id"] for a in listed if a.get("name") == name]
        if not matches:
            raise LookupError(f"no {collection} asset named {name!r} in Dash0")
        return matches[-1]
