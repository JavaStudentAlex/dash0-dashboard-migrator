"""Command line for the Datadog to Dash0 migrator: ``migrate``, ``import`` and ``fetch-datadog``."""

import argparse
import json
import os
import re
from collections.abc import Callable
from pathlib import Path

from dd2dash0.clients import APIError
from dd2dash0.clients.dash0 import (
    DEFAULT_API_URL,
    IMPORT_CHECK_RULE_PATH,
    IMPORT_DASHBOARD_PATH,
    Dash0Client,
)
from dd2dash0.clients.datadog import DatadogClient


def _read(path: Path) -> dict:
    """Load one JSON file.

    :param path: File to read.
    """
    return json.loads(path.read_text())


def _write(path: Path, payload: object) -> None:
    """Write ``payload`` as indented JSON, creating parent directories.

    :param path: Target file.
    :param payload: JSON-serialisable value.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n")


def _slug(name: str) -> str:
    """Return a lowercase file-name-safe form of ``name``.

    :param name: Human-readable asset name.
    """
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def _migrate(args: argparse.Namespace) -> int:
    """Compile a Datadog dashboard and monitors to Dash0 files in ``args.out``.

    :param args: Parsed ``migrate`` arguments.
    :returns: Exit code 0.
    """
    # Imported here: the pipeline lives on the core branch, and import/fetch must work without it.
    from dd2dash0.pipeline import migrate

    monitor_files = [f for p in args.monitors for f in (sorted(p.glob("*.json")) if p.is_dir() else [p])]
    result = migrate(_read(args.dashboard), [_read(f) for f in monitor_files], seed=args.seed)
    _write(args.out / "dashboard.perses.json", result.dashboard)
    for n, rule in enumerate(result.check_rules, 1):
        _write(args.out / "check_rules" / f"{n:02d}_{_slug(rule['name'])}.json", rule)
    _write(args.out / "report.json", result.report)
    (args.out / "report.md").write_text(result.report_markdown())
    print(result.report["summary"])
    return 0


def _stored_id(asset: dict) -> str | None:
    """Return the id that Dash0 put into an import answer, if any.

    :param asset: Import answer (check rule: top-level ``id``; dashboard: ``metadata.dash0Extensions.id``).
    """
    return asset.get("id") or asset.get("metadata", {}).get("dash0Extensions", {}).get("id")


def _stored_name(asset: dict) -> str | None:
    """Return the name of a stored dashboard (``metadata.name``) or check rule (``name``).

    :param asset: Asset as read back from Dash0.
    """
    return asset.get("name") or asset.get("metadata", {}).get("name")


def _import(args: argparse.Namespace, dash0_factory: Callable[[str], Dash0Client]) -> int:
    """Import the files written by ``migrate`` into Dash0 and read each asset back.

    :param args: Parsed ``import`` arguments.
    :param dash0_factory: Builds a client for a dataset; not called on ``--dry-run``.
    :returns: 0 if every read-back matched, else 1.
    """
    dashboard = _read(args.out / "dashboard.perses.json")
    rules = [_read(f) for f in sorted((args.out / "check_rules").glob("*.json"))]
    if args.dry_run:
        base = os.environ.get("DASH0_API_URL", DEFAULT_API_URL)
        print(f"dashboard\t{dashboard['metadata']['name']}\tPOST {base}{IMPORT_DASHBOARD_PATH}?dataset={args.dataset}")
        for rule in rules:
            print(f"check-rule\t{rule['name']}\tPOST {base}{IMPORT_CHECK_RULE_PATH}?dataset={args.dataset}")
        return 0

    client = dash0_factory(args.dataset)
    assets = [("dashboard", "dashboards", dashboard["metadata"]["name"], dashboard, client.import_dashboard, client.get_dashboard)]
    assets += [("check-rule", "alerting/check-rules", r["name"], r, client.import_check_rule, client.get_check_rule) for r in rules]
    failed = 0
    for kind, collection, name, payload, put, get in assets:
        stored = put(payload)
        asset_id = _stored_id(stored) or client.find_id(collection, name)
        # A failed read-back is reported per asset so that the remaining assets are still migrated.
        try:
            status = "ok" if _stored_name(get(asset_id)) == name else "failed: name mismatch"
        except APIError as error:
            status = f"failed: {error}"
        failed += status != "ok"
        print(f"{kind}\t{name}\t{asset_id}\tread-back {status}")
    return 1 if failed else 0


def _fetch_datadog(args: argparse.Namespace, datadog_factory: Callable[[], DatadogClient]) -> int:
    """Save a Datadog dashboard and monitors in export format under ``args.out``.

    :param args: Parsed ``fetch-datadog`` arguments.
    :param datadog_factory: Builds the Datadog client.
    :returns: Exit code 0.
    """
    client = datadog_factory()
    _write(args.out / "dashboard.json", client.get_dashboard(args.dashboard_id))
    for monitor_id in args.monitor_ids.split(","):
        _write(args.out / "monitors" / f"{monitor_id}.json", client.get_monitor(monitor_id))
    print(f"saved dashboard {args.dashboard_id} and {len(args.monitor_ids.split(','))} monitors to {args.out}")
    return 0


def main(
    argv: list[str] | None = None,
    *,
    dash0_factory: Callable[[str], Dash0Client] = Dash0Client.from_env,
    datadog_factory: Callable[[], DatadogClient] = DatadogClient.from_env,
) -> int:
    """Parse ``argv`` and run one subcommand.

    :param argv: Arguments without the program name; ``None`` uses ``sys.argv``.
    :param dash0_factory: Builds the Dash0 client from a dataset; tests inject a mock.
    :param datadog_factory: Builds the Datadog client; tests inject a mock.
    :returns: Process exit code.
    """
    parser = argparse.ArgumentParser(prog="dd2dash0", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    migrate = sub.add_parser("migrate", help="compile Datadog JSON to Dash0 files")
    migrate.add_argument("--dashboard", type=Path, required=True)
    migrate.add_argument("--monitors", type=Path, nargs="+", required=True, help="directory or monitor JSON files")
    migrate.add_argument("--out", type=Path, required=True)
    migrate.add_argument("--seed", type=int, default=7)

    imp = sub.add_parser("import", help="import migrate output into Dash0 and read it back")
    imp.add_argument("--out", type=Path, required=True)
    imp.add_argument("--dataset", default="default")
    imp.add_argument("--dry-run", action="store_true")

    fetch = sub.add_parser("fetch-datadog", help="save a Datadog dashboard and monitors as JSON")
    fetch.add_argument("--dashboard-id", required=True)
    fetch.add_argument("--monitor-ids", required=True, help="comma-separated monitor ids")
    fetch.add_argument("--out", type=Path, required=True)

    args = parser.parse_args(argv)
    if args.command == "migrate":
        return _migrate(args)
    if args.command == "import":
        return _import(args, dash0_factory)
    return _fetch_datadog(args, datadog_factory)
