"""Bounded AB-MCTS (Adaptive Branching MCTS, Sakana AI "Wider or Deeper?") over a fixed strategy registry.

The root chooses by Thompson sampling between GEN (go wider: expand an untried strategy)
and CONT (go deeper: evaluate the next variant of a Thompson-selected strategy).
"""
import random
from collections.abc import Callable
from dataclasses import dataclass

REGISTRY = ("direct", "composed", "partial_with_warning", "manual")


@dataclass(frozen=True)
class SearchResult:
    """Best candidate and the trace ``(iteration, action, strategy, variant, reward)``."""

    strategy: str
    variant: object
    reward: float
    iterations: int
    trace: tuple[tuple, ...]


def search(strategies: tuple[str, ...], variants: tuple, reward: Callable[[str, object], float], *,
           seed: int = 7, budget: int = 32) -> SearchResult:
    """Return the best ``(strategy, variant)`` by reward within ``budget`` evaluations.

    Stops early on a reward of 1.0 or when every candidate is evaluated. The same seed
    gives the same trace.

    :raises ValueError: if a strategy is not in :data:`REGISTRY`.
    """
    unknown = sorted(set(strategies) - set(REGISTRY))
    if unknown:
        raise ValueError(f"strategies outside the registry: {unknown}")
    rng = random.Random(seed)
    untried = list(strategies)
    children: dict[str, list[float]] = {}
    posterior = {"GEN": [1.0, 1.0], "CONT": [1.0, 1.0]}
    best, trace = None, []
    for iteration in range(1, budget + 1):
        open_children = [s for s, rewards in children.items() if len(rewards) < len(variants)]
        if not untried and not open_children:
            break
        wider = rng.betavariate(*posterior["GEN"]) >= rng.betavariate(*posterior["CONT"])
        action = "GEN" if untried and (wider or not open_children) else "CONT"
        if action == "GEN":
            strategy = untried.pop(rng.randrange(len(untried)))
            children[strategy] = []
        else:
            strategy = max(open_children, key=lambda s: rng.betavariate(
                1 + sum(children[s]), 1 + len(children[s]) - sum(children[s])))
        variant = variants[len(children[strategy])]
        value = reward(strategy, variant)
        children[strategy].append(value)
        posterior[action][0] += value
        posterior[action][1] += 1 - value
        trace.append((iteration, action, strategy, variant, value))
        if best is None or value > best[2]:
            best = (strategy, variant, value)
        if value >= 1.0:
            break
    return SearchResult(*best, len(trace), tuple(trace))
