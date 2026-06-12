"""Judge calibration runner — Cohen κ ≥ 0.6 (Landis & Koch substantial-agreement).

Implements spec §7.3 (calibration corpus shape) + §7.4 (agreement metric + cadence).
Pure-stdlib κ (no numpy / scipy dep). Discretises [0,1] rubric scores into
equal-width bins before computing standard Cohen κ on the confusion matrix.

Bin edge convention (default 3 bins): ``[0.0, 0.33), [0.33, 0.66), [0.66, 1.0]``
— lower-inclusive / upper-exclusive except the top bin which is closed on the
right so 1.0 lands in the highest bin (not out of range).

Calibration verdict threshold (κ ≥ 0.6) is independent of the rubric-axis
per-record pass threshold (``RUBRIC_PASS_THRESHOLD`` in ``gates/_constants.py``);
the coincidental numeric match is documented in spec decision #124 / #126.
"""

from __future__ import annotations

import bisect
from collections import Counter
from dataclasses import dataclass, field
from typing import Protocol

from nanobot.evolve._base import EvolveBase
from nanobot.evolve.schemas import RubricScore

# Landis & Koch 1977: κ ≥ 0.61 = "substantial"; spec §7.4 / decision #126
# rounds to 0.6 as the hard gate.
CALIBRATION_KAPPA_THRESHOLD: float = 0.6

# Threshold-compare tolerance. Landis & Koch threshold is inclusive (κ ≥ 0.6);
# FP accumulation in per-axis κ + mean/3 can underflow 0.6 by ~1e-16 on
# borderline corpora, so a tiny epsilon prevents spurious calibration failures
# when the true κ is exactly at the boundary.
_KAPPA_EPSILON: float = 1e-9

# Rubric axes evaluated per record. Mirrors RubricScore non-aggregate fields
# (§7.2 — process / output / token are the 3 axes; ``aggregate`` is the
# pre-computed scalar and is not κ'd independently).
RUBRIC_AXES: tuple[str, ...] = ("process", "output", "token")


# Intentional @dataclass (not EvolveBase): test/runtime input record, not serialised
# into the RunManifest sidecar — keeps fixture construction terse without alias plumbing.
@dataclass(frozen=True)
class CalibrationRecord:
    """One human-labelled calibration sample.

    ``human_scores`` maps axis name → float ∈ [0, 1]. ``input_payload`` carries
    whatever the judge pool needs to produce a JudgeResult; opaque to κ math.
    Spec §7.3 prescribes a richer corpus shape (``label_provenance`` /
    ``label_date`` / ``input`` / ``candidate``); we keep the minimal
    κ-relevant subset here and let consumers carry the rest in
    ``input_payload``.
    """

    record_id: str
    human_scores: dict[str, float]
    input_payload: dict[str, object] = field(default_factory=dict)


class _JudgeScorer(Protocol):
    """Duck-typed shim — anything callable as ``pool.score(record) -> RubricScore``.

    The frozen Pydantic ``JudgePool`` does not yet expose a ``score`` method
    (M4 t-04 / t-05 only defined the config + result types). ``calibrate``
    invokes ``pool.score(record)`` so tests can pass a stub now and the real
    pool can grow the method in a follow-up without breaking this signature.

    TODO(m4-followup CF-cc-a): wire the real ``JudgePool.score`` entry point
    during the t-14 / t-15 pipeline task — see ``m4-carry-forward.md`` §9.
    """

    def score(self, record: CalibrationRecord) -> RubricScore: ...


class CalibrationReport(EvolveBase):
    """Outcome of one calibration run.

    ``kappa_per_axis`` keys are rubric axes (§7.2: ``process`` / ``output`` /
    ``token``). ``kappa_mean`` is the unweighted arithmetic mean across axes
    (§7.4 — "逐 axis 计算 then mean across axes"). ``passed`` is the spec-locked
    verdict (``kappa_mean >= CALIBRATION_KAPPA_THRESHOLD``).
    """

    kappa_mean: float
    kappa_per_axis: dict[str, float]
    passed: bool


def _bin_cutoffs(bins: int) -> list[float]:
    """Internal upper-cutoffs (length ``bins - 1``) used by ``_bin_index``.

    DUAL CONVENTION (intentional, do not "unify"):

    * ``bins == 3`` — returns the SPEC-PINNED LITERAL ``[0.33, 0.66]`` (the
      truncated-decimal form from spec §7.2 / decision #124, NOT mathematical
      thirds ``[1/3, 2/3] ≈ [0.3333…, 0.6666…]``). The truncated form is what
      the human-labelling guideline shipped to annotators uses, so the κ math
      must match it exactly or human/judge bin assignments diverge silently.
      This is the production path.

      Concrete worked examples (under ``bisect_right([0.33, 0.66], v)``):

        * ``_bin_index(0.33, 3)`` → 1 (0.33 is NOT strictly less than 0.33;
          ``bisect_right`` places the equal value past the cutoff).
        * ``_bin_index(0.333, 3)`` → 1 (0.333 > 0.33, past first cutoff).
        * ``_bin_index(0.3333, 3)`` → 1 (the mathematical 1/3 lands in bin 1
          because 0.3333 > 0.33 — there is a ~0.003 quantization gap rounding
          DOWN from mathematical thirds to the spec-pinned cutoffs).
        * ``_bin_index(0.32, 3)`` → 0 (0.32 < 0.33, before first cutoff).

    * ``bins != 3`` — equal-width fallback ``[i / bins for i in 1..bins-1]``
      (e.g. bins=4 → ``[0.25, 0.5, 0.75]``). Provided for future rubric
      revisions; NOT spec-pinned and NOT exercised by the production gate.
      A caller passing a variable ``bins`` that drifts off 3 silently
      switches semantics — call sites should treat ``bins`` as a constant.
    """
    if bins == 3:
        return [0.33, 0.66]
    return [i / bins for i in range(1, bins)]


def _bin_index(value: float, bins: int) -> int:
    """Bin a ``[0,1]`` score into ``[0, bins)``.

    Lower-inclusive / upper-exclusive on every bin except the top bin which
    is closed on the right (so 1.0 maps to ``bins - 1`` rather than going
    out of range). Uses ``bisect_right`` against ``_bin_cutoffs(bins)``.
    Out-of-[0, 1] inputs raise ValueError.
    """
    if value < 0.0 or value > 1.0:
        raise ValueError(f"score out of [0,1]: {value!r}")
    cutoffs = _bin_cutoffs(bins)
    # bisect_right gives count of cutoffs <= value → exactly the bin index for
    # lower-inclusive / upper-exclusive semantics. Top-bin closed-right falls
    # out naturally: value == 1.0 sits past every cutoff → index == bins - 1.
    return bisect.bisect_right(cutoffs, value)


def compute_cohen_kappa(
    human: list[float], judge: list[float], *, bins: int = 3
) -> float:
    """Cohen κ on discretised rubric scores.

    Discretises both lists into ``bins`` equal-width bins (see ``_bin_index``
    for the edge convention), builds the confusion matrix, then computes:

        po = sum(diag) / N                          # observed agreement
        pe = sum(row_i * col_i for i in bins) / N²  # chance agreement
        κ  = (po - pe) / (1 - pe)

    Degenerate ``pe == 1`` case (both raters concentrate every sample into a
    single bin): defined as κ = 1.0 when ``po == 1`` (perfect agreement) else
    0.0 (avoids divide-by-zero; matches scikit-learn convention).

    Raises ``ValueError`` for empty / mismatched-length inputs, or scores
    outside ``[0, 1]``.
    """
    if len(human) != len(judge):
        raise ValueError(
            f"length mismatch: len(human)={len(human)} != len(judge)={len(judge)}"
        )
    if len(human) == 0:
        raise ValueError("empty input")
    if bins < 2:
        raise ValueError(f"bins must be >= 2 (got {bins})")

    n = len(human)
    h_bins = [_bin_index(v, bins) for v in human]
    j_bins = [_bin_index(v, bins) for v in judge]

    row_counts: Counter[int] = Counter(h_bins)
    col_counts: Counter[int] = Counter(j_bins)
    diag = sum(1 for h, j in zip(h_bins, j_bins) if h == j)

    po = diag / n
    pe = sum(row_counts[i] * col_counts[i] for i in range(bins)) / (n * n)

    if pe >= 1.0:
        # Both raters put every sample in the same single bin → chance
        # agreement is total; κ is undefined by the standard formula.
        return 1.0 if po >= 1.0 else 0.0
    return (po - pe) / (1.0 - pe)


def calibrate(records: list[CalibrationRecord], pool: _JudgeScorer) -> CalibrationReport:
    """Run the judge pool against ``records`` and report per-axis κ + verdict.

    For each record we call ``pool.score(record)`` to obtain a ``RubricScore``;
    we then compute Cohen κ per axis (process / output / token) against the
    human gold labels, average across axes, and compare to
    ``CALIBRATION_KAPPA_THRESHOLD``. Returns a ``CalibrationReport``.

    Raises ``ValueError`` for an empty corpus (κ is undefined) or for a record
    missing one of the rubric axes in ``human_scores``.
    """
    if not records:
        raise ValueError("calibration corpus is empty")

    judge_scores: list[RubricScore] = [pool.score(r) for r in records]

    kappa_per_axis: dict[str, float] = {}
    for axis in RUBRIC_AXES:
        human_axis: list[float] = []
        judge_axis: list[float] = []
        for rec, js in zip(records, judge_scores):
            if axis not in rec.human_scores:
                raise ValueError(
                    f"record {rec.record_id!r} missing human score for axis {axis!r}"
                )
            human_axis.append(rec.human_scores[axis])
            judge_axis.append(getattr(js, axis))
        kappa_per_axis[axis] = compute_cohen_kappa(human_axis, judge_axis)

    kappa_mean = sum(kappa_per_axis.values()) / len(kappa_per_axis)
    return CalibrationReport(
        kappa_mean=kappa_mean,
        kappa_per_axis=kappa_per_axis,
        passed=kappa_mean >= CALIBRATION_KAPPA_THRESHOLD - _KAPPA_EPSILON,
    )
