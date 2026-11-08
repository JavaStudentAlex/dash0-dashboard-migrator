"""Tests for the SIFT evidence gate."""
import pytest

from dd2dash0 import sift
from dd2dash0.datadog_parser import parse_query
from dd2dash0.ontology import DynamicOntologyProposer, Ontology
from dd2dash0.promql import compile_query

ONTOLOGY = Ontology(proposer=DynamicOntologyProposer())


def _verdict(text, strategy, window=None, time_aggregation=None):
    """Compile one query with a strategy and run the gate on it."""
    query = parse_query(text)
    concept = ONTOLOGY.resolve(query.metric)
    promql = compile_query(query, concept, ONTOLOGY, strategy, window, time_aggregation)
    return sift.evaluate(query, concept, strategy, promql, time_aggregation)


def test_exact_certified_mapping_is_migrated():
    """A certified counter with a direct PromQL form passes all four checks."""
    verdict = _verdict("sum:reisy.search.requests{service:travel-service}.as_count()", "direct")
    assert (verdict.score, verdict.status, verdict.warnings) == (1.0, "migrated", ())
    assert all(verdict.checks.values())


def test_percentile_is_partial_with_explicit_warnings():
    """p95 has two admissible strategies; the composed one is an approximation with warnings."""
    query = parse_query("p95:reisy.search.latency{service:travel-service}")
    assert sift.admissible(query, ONTOLOGY.resolve(query.metric)) == ("composed", "partial_with_warning")
    verdict = _verdict(query.raw, "composed", "10m", "avg")
    assert verdict.status == "partial" and verdict.score == pytest.approx(0.8 * 0.9)
    assert any("histogram_quantile" in w for w in verdict.warnings)
    assert any("aggregation order" in w for w in verdict.warnings)


def test_candidate_concept_is_never_silently_accepted():
    """An uncertified candidate fails Stop and stays partial with a manual-review warning."""
    verdict = _verdict("avg:reisy.cache.hit_ratio{service:travel-service}", "partial_with_warning")
    assert verdict.status == "partial" and not verdict.checks["stop"]
    assert any("uncertified mapping, manual review" in w for w in verdict.warnings)


def test_no_equivalent_is_unsupported():
    """``anomalies`` has no PromQL equivalent: no admissible strategy, score 0."""
    query = parse_query("anomalies(avg:reisy.search.latency{service:travel-service}, 'basic', 2)")
    assert sift.admissible(query, ONTOLOGY.resolve(query.metric)) == ()
    verdict = _verdict(query.raw, "manual")
    assert (verdict.score, verdict.status) == (0.0, "unsupported")
    assert "anomalies" in verdict.warnings[0]
