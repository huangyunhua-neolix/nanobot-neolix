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
    for i, gate in enumerate(GATES):
        assert gate.name.startswith(f"{i+1}-"), (i, gate.name)


def test_no_orphan_gate_subclass():
    production_subclasses = {
        c for c in Gate._subclasses
        if c.__module__.startswith("nanobot.evolve.gates.")
        and not inspect.isabstract(c)
    }
    registered = {type(g) for g in GATES}
    orphans = production_subclasses - registered
    assert not orphans, f"orphan production gate subclass(es): {orphans}"
