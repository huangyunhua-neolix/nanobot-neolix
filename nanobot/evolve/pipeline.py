"""GEPA + DSPy optimisation pipeline bootstrap (spec §3.5, §3.5.1).

The DSPy + GEPA dependencies are heavy and gated behind the optional
``nanobot[evolve]`` extra (spec §3.5.1). This module therefore MUST NOT
import them at module load time — importing ``nanobot.evolve.pipeline``
without the extra installed must still succeed and expose ``build_pipeline``.
The lazy guard inside ``_lazy_import_gepa`` raises
:class:`EvolveExtraNotInstalled` only when the pipeline is actually invoked.
"""

from nanobot.evolve.exceptions import EvolveExtraNotInstalled


def _lazy_import_gepa():
    """Import GEPA + DSPy on demand, surfacing the install hint on failure."""
    try:
        import dspy  # noqa: F401
        import gepa  # noqa: F401
    except ImportError as e:
        raise EvolveExtraNotInstalled(
            f"M4 evolve harness needs DSPy + GEPA. {EvolveExtraNotInstalled.INSTALL_HINT}"
        ) from e
    return dspy, gepa


def build_pipeline(*, skill_name: str, judge_pool, baseline, eval_records):
    """GEPA bootstrap entrypoint.

    Wires a GEPA ``optimize(metric_fn=...)`` loop against the rubric judge
    pool over the 4-tier eval records, returning a candidate-selection
    pipeline. Lazy-imports DSPy + GEPA so callers without the
    ``nanobot[evolve]`` extra fail loudly only at call time.
    """
    _dspy, _gepa = _lazy_import_gepa()
    # Intentionally deferred: GEPA optimisation wiring lands in M5 alongside
    # the real eval-tier loop (see CF-t14-pipeline-wiring). t-14 is the
    # lazy-import scaffold only.
    raise NotImplementedError(
        "GEPA optimization wiring lands in M5 — see CF-t14-pipeline-wiring"
    )
