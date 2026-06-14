"""Deprecated M4 GEPA bootstrap shim.

M5.1 invokes external optimizers only through
``nanobot.evolve.optimizer.OptimizerAdapter``. This module remains importable for
older callers, but it must not import DSPy, GEPA, Darwinian Evolver, or any other
optimizer package, even lazily.
"""

from nanobot.evolve.exceptions import EvolveExtraNotInstalled


def build_pipeline(*, skill_name: str, judge_pool, baseline, eval_records):
    del skill_name, judge_pool, baseline, eval_records
    raise EvolveExtraNotInstalled(
        "M5.1 removed the in-process GEPA pipeline path; use the subprocess "
        "optimizer adapter via `nanobot evolve run --optimizer-command ...`."
    )
