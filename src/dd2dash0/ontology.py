"""Seed ontology of certified metric concepts plus a metadata-only proposer for unknown metrics.

The proposer follows the auto-ontology idea: build concepts from metadata, but ground
authoritative output only in certified terms. Proposed concepts are always ``candidate``.
"""
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

SEED = Path(__file__).parent / "ontologies" / "reisy_travel_search.json"


@dataclass(frozen=True)
class Concept:
    """Mapping of one Datadog metric to one OTel metric, with status and provenance."""

    datadog_metric: str
    datadog_type: str
    otel_metric_name: str
    instrument: str
    unit: str
    status: str
    provenance: str
    confidence: float = 1.0
    rationale: str = ""


class CandidateProposer(Protocol):
    """Source of candidate concepts for unknown metrics, e.g. a future LLM proposer."""

    def propose(self, metric: str) -> Concept | None:
        """Return a ``candidate`` concept for ``metric`` or ``None``."""


# Order matters: the first token family that matches decides the instrument.
_RULES = (
    ({"ratio", "pct"}, "gauge", "gauge", "1"),
    ({"count", "calls", "requests", "errors"}, "count", "counter", "{count}"),
    ({"latency", "duration", "time"}, "distribution", "histogram", "ms"),
    ({"cost", "usd"}, "gauge", "gauge", "USD"),
)


class DynamicOntologyProposer:
    """Propose candidate concepts from metric-name tokens only."""

    def propose(self, metric: str) -> Concept | None:
        """Return a candidate concept if a name token implies an instrument, else ``None``."""
        tokens = set(re.split(r"[._]", metric))
        for words, datadog_type, instrument, unit in _RULES:
            hits = sorted(tokens & words)
            if hits:
                return Concept(metric, datadog_type, metric, instrument, unit, "candidate",
                               "DynamicOntologyProposer (metric-name metadata)", confidence=0.6,
                               rationale=f"name tokens {hits} imply a {instrument} in {unit}")
        return None


class Ontology:
    """Certified seed concepts, the tag-to-label map and an optional candidate proposer."""

    def __init__(self, path: Path = SEED, proposer: CandidateProposer | None = None):
        """Load the seed ontology from ``path``."""
        data = json.loads(path.read_text())
        self.concepts = {c["datadog_metric"]: Concept(**c) for c in data["concepts"]}
        self.tag_labels = data["tag_labels"]
        self.proposer = proposer

    def label(self, tag: str) -> str:
        """Map a Datadog tag key to its Dash0 OTel label; other keys stay unchanged."""
        return self.tag_labels.get(tag, tag)

    def resolve(self, metric: str) -> Concept | None:
        """Return the seed concept, else the proposer's candidate, else ``None``.

        :raises ValueError: if a proposer returns anything but a candidate.
        """
        if metric in self.concepts:
            return self.concepts[metric]
        concept = self.proposer.propose(metric) if self.proposer else None
        if concept is not None and concept.status != "candidate":
            raise ValueError(f"proposer returned status {concept.status!r} for {metric}; only candidate is allowed")
        return concept
