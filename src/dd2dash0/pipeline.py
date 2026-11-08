"""End-to-end migration: parse, resolve concepts, gate with SIFT, search, compile, report."""
from dataclasses import dataclass

from dd2dash0 import abmcts, perses, report, sift
from dd2dash0.check_rules import check_rule
from dd2dash0.datadog_parser import parse_dashboard, parse_monitor
from dd2dash0.ir import Diagnostic, Formula
from dd2dash0.ontology import DynamicOntologyProposer, Ontology
from dd2dash0.promql import compile_formula, compile_query


@dataclass
class MigrationResult:
    """Perses dashboard, Dash0 check rules and the migration report."""

    dashboard: dict
    check_rules: list[dict]
    report: dict

    def report_markdown(self) -> str:
        """Render the report as a markdown table."""
        return report.markdown(self.report)


def _migrate_formula(formula: Formula, ontology: Ontology, seed: int, window: str | None = None,
                     time_aggregation: str | None = None) -> tuple[str | None, str, sift.SiftVerdict]:
    """Return PromQL (``None`` if unsupported), the strategy label and the combined verdict.

    One admissible strategy takes the deterministic fast path; several start AB-MCTS. The
    final status is always the SIFT verdict of the chosen candidate, never the search reward.
    """
    compiled, strategies, verdicts = {}, [], []
    for name, query in formula.queries.items():
        concept = ontology.resolve(query.metric)
        options = sift.admissible(query, concept)

        def build(strategy, variant, query=query, concept=concept):
            """Compile one candidate and gate it."""
            promql = compile_query(query, concept, ontology, strategy, variant, time_aggregation)
            return promql, sift.evaluate(query, concept, strategy, promql, time_aggregation)

        strategy, variant = (options[0] if options else "manual"), window
        if len(options) > 1:
            # Monitor windows are fixed; only dashboards may vary the range variable.
            variants = (window,) if window else (None, "$__interval")
            found = abmcts.search(options, variants, lambda s, v: build(s, v)[1].score, seed=seed)
            strategy, variant = found.strategy, found.variant
        compiled[name], verdict = build(strategy, variant)
        strategies.append(strategy)
        verdicts.append(verdict)
    verdict = sift.combine(verdicts)
    promql = None if verdict.status == "unsupported" else compile_formula(formula, compiled)
    return promql, "+".join(dict.fromkeys(strategies)), verdict


def migrate(dashboard: dict, monitors: list[dict], *, seed: int = 7) -> MigrationResult:
    """Migrate one Datadog dashboard and its monitors to Dash0; unsupported items go only to the report."""
    ontology = Ontology(proposer=DynamicOntologyProposer())
    title, widgets = parse_dashboard(dashboard)
    diagnostics, panels, rules = [], [], []
    for widget in widgets:
        item = f"widget {widget.id}: {widget.title}"
        if widget.type not in perses.PANEL_KINDS:
            diagnostics.append(Diagnostic("dashboard", item, "unsupported", "manual", 0.0,
                                          (f"widget type {widget.type} has no Perses panel",)))
            continue
        results = [_migrate_formula(f, ontology, seed) for f in widget.formulas]
        verdict = sift.combine([v for _, _, v in results]) if results else sift.SiftVerdict(1.0, "migrated", {}, ())
        strategy = "+".join(dict.fromkeys(s for _, s, _ in results)) or "direct"
        if verdict.status != "unsupported":
            panels.append((widget, [promql for promql, _, _ in results]))
        diagnostics.append(Diagnostic("dashboard", item, verdict.status, strategy, verdict.score, verdict.warnings))
    for data in monitors:
        item = f"monitor {data['id']}: {data['name']}"
        try:
            monitor = parse_monitor(data)
        except ValueError as error:  # reported as unsupported, not dropped
            diagnostics.append(Diagnostic("monitor", item, "unsupported", "manual", 0.0, (str(error),)))
            continue
        promql, strategy, verdict = _migrate_formula(monitor.formula, ontology, seed, monitor.window,
                                                     monitor.time_aggregation)
        warnings = verdict.warnings
        if promql is not None:
            rule, option_warnings = check_rule(monitor, promql)
            rules.append(rule)
            warnings += option_warnings
        diagnostics.append(Diagnostic("monitor", item, verdict.status, strategy, verdict.score, warnings))
    return MigrationResult(perses.dashboard(title, panels), rules, report.build_report(diagnostics))
