"""Tests for the seed ontology and the dynamic ontology proposer."""
import pytest

from dd2dash0.ontology import Concept, DynamicOntologyProposer, Ontology


def test_seed_concepts_are_certified_with_provenance():
    """The seed holds six certified concepts and maps tags to OTel labels."""
    ontology = Ontology()
    concept = ontology.resolve("reisy.search.latency")
    assert (concept.instrument, concept.unit, concept.status) == ("histogram", "ms", "certified")
    assert concept.provenance == "REISY travel-service instrumentation spec v1"
    assert len(ontology.concepts) == 6
    assert ontology.resolve("reisy.cache.hit_ratio") is None
    assert [ontology.label(t) for t in ("service", "env", "mode")] == ["service_name", "deployment_environment_name", "mode"]


def test_proposer_builds_candidates_from_metadata_only():
    """The proposer reads name tokens, returns candidates only, and abstains without evidence."""
    proposer = DynamicOntologyProposer()
    concept = Ontology(proposer=proposer).resolve("reisy.cache.hit_ratio")
    assert (concept.instrument, concept.unit, concept.status) == ("gauge", "1", "candidate")
    assert "ratio" in concept.rationale and 0 < concept.confidence < 1
    assert proposer.propose("reisy.queue.depth") is None
    assert proposer.propose("svc.checkout.latency").instrument == "histogram"


def test_resolve_rejects_a_proposer_that_certifies():
    """A plugged-in proposer (e.g. an LLM) can never certify a mapping."""

    class Certifier:
        """Misbehaving proposer that claims certification."""

        def propose(self, metric):
            """Return a certified concept, which the ontology must refuse."""
            return Concept(metric, "gauge", metric, "gauge", "1", "certified", "llm")

    with pytest.raises(ValueError, match="candidate"):
        Ontology(proposer=Certifier()).resolve("x.y")
