"""Contract tests for spec §6.4.1: GATES ordering + no orphan production Gate subclasses.

Enforces the Decision #122 dual-registry contract: every concrete production
Gate subclass under ``nanobot.evolve.gates`` must be instantiated in the ordered
``GATES`` list, and each instance's ``name`` must carry the ``"{i+1}-"`` prefix
matching its position.
"""

import inspect

# Force submodule imports (registers concrete gates into GATES + _subclasses).
import nanobot.evolve.gates.cache_compat  # noqa: F401
import nanobot.evolve.gates.skill_size  # noqa: F401
import nanobot.evolve.gates.test_pass  # noqa: F401
from nanobot.evolve.gates import GATES, Gate


def test_gates_ordering_matches_name_prefix():
    assert len(GATES) >= 1, "GATES must not be empty — contract test would silently pass"
    for i, gate in enumerate(GATES):
        assert gate.name.startswith(f"{i+1}-"), (
            f"GATES[{i}] name={gate.name!r} does not start with '{i+1}-'"
        )


def test_gate_names_are_unique():
    names = [g.name for g in GATES]
    assert len(set(names)) == len(names), f"duplicate gate names in GATES: {names}"


def test_no_orphan_gate_subclass():
    production_subclasses = {
        c for c in Gate._subclasses
        if c.__module__.startswith("nanobot.evolve.gates.")
        and not inspect.isabstract(c)
    }
    registered = {type(g) for g in GATES}
    orphans = production_subclasses - registered
    assert not orphans, f"orphan production gate subclass(es): {orphans}"


def test_e2e_gates_iterate_with_shared_fake(shared_passing_candidate, shared_baseline):
    """Smoke: iterating GATES with a shared fake (Candidate, Baseline) yields a
    GateResult per gate without TypeError on field-shape divergence. Designed to
    fail loudly when t-11 lands real Pydantic models and a gate's duck-typing
    drifts from the canonical model shape."""
    results = []
    for gate in GATES:
        r = gate.evaluate(shared_passing_candidate, shared_baseline)
        results.append(r)
        assert r.gate_name == gate.name
        assert r.verdict in ("pass", "fail")
    assert len(results) == len(GATES)
