# dash0-dashboard-migrator (`dd2dash0`)

Migrates Datadog dashboards **and** monitors to Dash0: Perses dashboards and Dash0 check rules
(Prometheus alert rules).

- Deterministic compiler: Datadog JSON -> intermediate representation -> PromQL -> Perses / check rules.
- Ontology of Datadog metrics, tags and aggregations mapped to OpenTelemetry/Prometheus names.
- SIFT evidence gate: a mapping is used only when the evidence for it passes the gate.
- Bounded AB-MCTS search decides ambiguous mappings with a fixed seed, so runs are reproducible.
- Dynamic ontology proposer, modelled on NVIDIA auto-ontology, suggests new mappings for unknown metrics.
- Sample workload: REISY travel-service search telemetry.

## Install

```sh
uv venv && uv pip install -e '.[dev]'
uv run pytest -q
```

## Usage

```sh
# 1. Save Datadog JSON (needs DD_API_KEY, DD_APP_KEY, optional DD_SITE)
dd2dash0 fetch-datadog --dashboard-id abc-def-ghi --monitor-ids 101,102 --out dd/

# 2. Compile offline (no network)
dd2dash0 migrate --dashboard dd/dashboard.json --monitors dd/monitors --out out/ [--seed 7]
#    -> out/dashboard.perses.json, out/check_rules/NN_<slug>.json, out/report.json, out/report.md

# 3. Import into Dash0 and read every asset back (needs DASH0_AUTH_TOKEN)
dd2dash0 import --out out/ --dataset default --dry-run   # print targets only
dd2dash0 import --out out/ --dataset default             # exit code 1 if a read-back fails
```

`--monitors` takes a directory (all `*.json`) or one or more monitor files.
`python -m dd2dash0` works the same as `dd2dash0`.

## Environment variables

| Variable | Use | Default |
|---|---|---|
| `DASH0_API_URL` | Dash0 API root | `https://api.europe-west4.gcp.dash0.com` |
| `DASH0_AUTH_TOKEN` | Dash0 auth token (sent as `Authorization: Bearer`) | required for `import` |
| `DD_API_KEY`, `DD_APP_KEY` | Datadog keys (`DD-API-KEY`, `DD-APPLICATION-KEY`) | required for `fetch-datadog` |
| `DD_SITE` | Datadog site, for example `datadoghq.eu` | `datadoghq.com` |

The tool never prints or stores tokens. API errors show the method, URL, HTTP status and response body.

## Dash0 API: verified and assumed

Source: the public OpenAPI document `https://www.dash0.com/docs/api-reference/openapi.json`
(OpenAPI 3.1, "Generated at: November 6, 2026"), and the pages
`https://www.dash0.com/docs/api-reference/operations/post/api/import/dashboard` and `.../import/check-rule`.
Checked on 2026-11-08 with curl. No live call was made.

Verified from the document:

- Auth: `bearerAuth`, `Authorization: Bearer <token>`.
- `POST /api/import/dashboard?dataset=<name>`: body and 200 answer are a `DashboardDefinition`
  (`kind: "Dashboard"`, `metadata.name` required, `spec` in Perses format). The id is
  `metadata.dash0Extensions.id`. Without an id, Dash0 creates a new dashboard with a generated id.
- `POST /api/import/check-rule?dataset=<name>`: body and 200 answer are a `PrometheusAlertRule`
  (`name` and `expression` required). The id is the top-level `id` field.
- Read-back: `GET /api/dashboards/{originOrId}?dataset=` and `GET /api/alerting/check-rules/{originOrId}?dataset=`.
- Errors: non-2xx answers carry an `ErrorResponse` (`{"error": {...}}`).
- Region API roots include `https://api.europe-west4.gcp.dash0.com` and `https://api.eu-west-1.aws.dash0.com`.

Assumed (not tested against a live Dash0 org):

- The id in the import answer is accepted at once by the GET endpoints (no delay).
- The target org has a dataset named `default` (the CLI default for `--dataset`).
- The check-rule page text says the id is in `metadata>dash0Extensions>id`, but the schema has a
  top-level `id` and no such field. The client uses the schema.
