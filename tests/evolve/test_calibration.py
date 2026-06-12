"""Tests for nanobot.evolve.judges.calibration — Cohen κ + verdict.

Spec refs: §7.3 (calibration corpus), §7.4 (κ ≥ 0.6 substantial-agreement gate).
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from nanobot.evolve.judges.calibration import (
    CALIBRATION_KAPPA_THRESHOLD,
    CalibrationRecord,
    CalibrationReport,
    _bin_cutoffs,
    _bin_index,
    calibrate,
    compute_cohen_kappa,
)
from nanobot.evolve.schemas import RubricScore

# ---------------------------------------------------------------------------
# compute_cohen_kappa — direct numeric tests
# ---------------------------------------------------------------------------


def test_kappa_perfect_agreement_is_one() -> None:
    # All three samples land in distinct bins (0.1→0, 0.5→1, 0.9→2);
    # po = 1, pe < 1 → κ = 1.
    assert compute_cohen_kappa([0.1, 0.5, 0.9], [0.1, 0.5, 0.9]) == pytest.approx(
        1.0, abs=1e-9
    )


def test_kappa_random_agreement_is_zero_or_negative() -> None:
    # Anti-correlated pairing: human picks bin 0 / 2 alternately, judge picks
    # the opposite bin → po=0, pe>0 → κ negative (worse than chance).
    # Derivation: h_bins=[0,2,0,2], j_bins=[2,0,2,0], diag=0 → po=0.
    # row_counts={0:2,2:2}, col_counts={0:2,2:2} → pe = (2*2 + 0 + 2*2)/16
    #   = 8/16 = 0.5. κ = (0 - 0.5)/(1 - 0.5) = -1.0 exactly.
    # Pinning to the exact value catches the common bug families:
    #   - swapped po/pe (would give -1/-1 → undefined / wrong)
    #   - returning abs(po-pe) instead of (po-pe)/(1-pe) → 0.5, not -1.0
    #   - population vs sample variance variants — all return != -1.0
    human = [0.1, 0.9, 0.1, 0.9]
    judge = [0.9, 0.1, 0.9, 0.1]
    kappa = compute_cohen_kappa(human, judge)
    assert kappa == pytest.approx(-1.0, abs=1e-9)


def test_threshold_constant_is_0_6() -> None:
    # Anchor the Landis & Koch decision (§7.4 / spec decision #126). A future
    # refactor that nudges this constant must update tests deliberately.
    assert CALIBRATION_KAPPA_THRESHOLD == 0.6


def test_kappa_empty_input_raises() -> None:
    with pytest.raises(ValueError, match="empty"):
        compute_cohen_kappa([], [])


def test_kappa_mismatched_length_raises() -> None:
    with pytest.raises(ValueError, match="length mismatch"):
        compute_cohen_kappa([0.1, 0.2], [0.1])


def test_kappa_all_same_bin_perfect_agreement() -> None:
    # Both lists fully inside bin 0 (po=1, pe=1) → degenerate case → κ=1.0
    # per scikit-learn convention documented in compute_cohen_kappa.
    human = [0.0, 0.1, 0.2]
    judge = [0.05, 0.15, 0.25]
    assert compute_cohen_kappa(human, judge) == pytest.approx(1.0, abs=1e-9)


def test_kappa_3_bins_default_matches_explicit() -> None:
    human = [0.1, 0.5, 0.9, 0.2, 0.7]
    judge = [0.15, 0.55, 0.95, 0.25, 0.7]
    assert compute_cohen_kappa(human, judge) == compute_cohen_kappa(
        human, judge, bins=3
    )


# ---------------------------------------------------------------------------
# Bin edge convention — 0.33 / 0.66 / 1.0
# ---------------------------------------------------------------------------


def test_bin_edges_lower_inclusive_upper_exclusive_except_top() -> None:
    """0.33 → bin 1, 0.66 → bin 2, 1.0 → bin 2 (top is closed-right).

    Strategy: pair (human, judge) where both lands always agree → κ=1, then
    flip only the human side near an edge — if the edge convention is wrong
    the kappa drops away from 1 in a detectable way.
    """
    # Both raters: 0.33 in bin 1, 0.66 in bin 2, 1.0 in bin 2. Pair each value
    # against a value in the SAME expected bin → κ=1 confirms the partition.
    human = [0.33, 0.66, 1.0, 0.0]
    judge = [0.40, 0.70, 0.99, 0.10]  # same bin per sample (1, 2, 2, 0)
    assert compute_cohen_kappa(human, judge) == pytest.approx(1.0, abs=1e-9)

    # Now place 0.32 (still bin 0) opposite 0.40 (bin 1) → at least one
    # disagreement → κ < 1.
    human2 = [0.32, 0.66, 1.0, 0.0]
    judge2 = [0.40, 0.70, 0.99, 0.10]
    assert compute_cohen_kappa(human2, judge2) < 1.0


def test_bin_edges_score_out_of_range_raises() -> None:
    with pytest.raises(ValueError, match="out of"):
        compute_cohen_kappa([1.5], [0.5])
    with pytest.raises(ValueError, match="out of"):
        compute_cohen_kappa([0.5], [-0.1])


# ---------------------------------------------------------------------------
# CalibrationReport dataclass shape
# ---------------------------------------------------------------------------


def test_calibration_report_dataclass_shape() -> None:
    r = CalibrationReport(
        kappa_mean=0.7,
        kappa_per_axis={"process": 0.8, "output": 0.6, "token": 0.7},
        passed=True,
    )
    assert r.kappa_mean == pytest.approx(0.7)
    assert r.kappa_per_axis["process"] == pytest.approx(0.8)
    assert r.passed is True


# ---------------------------------------------------------------------------
# calibrate(records, pool) — verdict around the κ ≥ 0.6 threshold
# ---------------------------------------------------------------------------


@dataclass
class _StubPool:
    """Maps each record_id → a canned RubricScore. Implements the
    ``score(record) -> RubricScore`` duck-typed protocol used by calibrate().
    """

    canned: dict[str, RubricScore] = field(default_factory=dict)

    def score(self, record: CalibrationRecord) -> RubricScore:
        return self.canned[record.record_id]


def _mk_record(record_id: str, p: float, o: float, t: float) -> CalibrationRecord:
    return CalibrationRecord(
        record_id=record_id,
        human_scores={"process": p, "output": o, "token": t},
    )


def _mk_score(p: float, o: float, t: float) -> RubricScore:
    # Aggregate is required by RubricScore; use default 0.4/0.4/0.2 weighting.
    return RubricScore(
        process=p, output=o, token=t, aggregate=0.4 * p + 0.4 * o + 0.2 * t
    )


def test_kappa_above_threshold_returns_true_verdict() -> None:
    # Six records, all three axes track human perfectly → per-axis κ=1.0 →
    # kappa_mean=1.0 ≥ 0.6 → passed.
    records = [
        _mk_record("r1", 0.1, 0.1, 0.1),
        _mk_record("r2", 0.5, 0.5, 0.5),
        _mk_record("r3", 0.9, 0.9, 0.9),
        _mk_record("r4", 0.2, 0.7, 0.1),
        _mk_record("r5", 0.8, 0.2, 0.9),
        _mk_record("r6", 0.4, 0.9, 0.3),
    ]
    pool = _StubPool(
        canned={
            "r1": _mk_score(0.1, 0.1, 0.1),
            "r2": _mk_score(0.5, 0.5, 0.5),
            "r3": _mk_score(0.9, 0.9, 0.9),
            "r4": _mk_score(0.2, 0.7, 0.1),
            "r5": _mk_score(0.8, 0.2, 0.9),
            "r6": _mk_score(0.4, 0.9, 0.3),
        }
    )
    report = calibrate(records, pool)
    assert report.passed is True
    assert report.kappa_mean == pytest.approx(1.0, abs=1e-9)
    assert set(report.kappa_per_axis) == {"process", "output", "token"}


def test_kappa_below_threshold_returns_false_verdict() -> None:
    # Anti-correlated judge — flip bin 0 ↔ bin 2 on every record → κ negative
    # on every axis → kappa_mean << 0.6 → passed=False.
    records = [
        _mk_record("r1", 0.1, 0.1, 0.1),
        _mk_record("r2", 0.9, 0.9, 0.9),
        _mk_record("r3", 0.1, 0.1, 0.1),
        _mk_record("r4", 0.9, 0.9, 0.9),
    ]
    pool = _StubPool(
        canned={
            "r1": _mk_score(0.9, 0.9, 0.9),
            "r2": _mk_score(0.1, 0.1, 0.1),
            "r3": _mk_score(0.9, 0.9, 0.9),
            "r4": _mk_score(0.1, 0.1, 0.1),
        }
    )
    report = calibrate(records, pool)
    assert report.passed is False
    assert report.kappa_mean < CALIBRATION_KAPPA_THRESHOLD


def test_calibrate_empty_records_raises() -> None:
    with pytest.raises(ValueError, match="empty"):
        calibrate([], _StubPool())


def test_calibrate_record_missing_axis_raises() -> None:
    bad = CalibrationRecord(
        record_id="bad", human_scores={"process": 0.5, "output": 0.5}  # missing token
    )
    pool = _StubPool(canned={"bad": _mk_score(0.5, 0.5, 0.5)})
    with pytest.raises(ValueError, match="missing human score for axis 'token'"):
        calibrate([bad], pool)


# ---------------------------------------------------------------------------
# R1 — direct _bin_index boundary pins
# ---------------------------------------------------------------------------


def test_bin_index_pins_3_bin_boundaries() -> None:
    """Lock the spec-pinned cutoffs ``[0.33, 0.66]`` (decision #124 / §7.2).

    These are LITERAL truncated decimals, NOT mathematical thirds. Off-by-one
    variants (``[0.34, 0.67]``, ``[1/3, 2/3]``, ``bisect_left`` instead of
    ``bisect_right``) would all violate at least one assertion here.
    """
    assert _bin_index(0.0, 3) == 0
    assert _bin_index(0.32, 3) == 0
    # 0.33 sits ON the lower cutoff → lower-inclusive on bin 1 (bisect_right
    # of 0.33 in [0.33, 0.66] = 1 → index 1). A bisect_left bug would put it
    # in bin 0 and fail here.
    assert _bin_index(0.33, 3) == 1
    assert _bin_index(0.6599, 3) == 1
    assert _bin_index(0.66, 3) == 2
    # Top edge is closed-right (else 1.0 would be out of range).
    assert _bin_index(1.0, 3) == 2


# ---------------------------------------------------------------------------
# R2 — intermediate κ value pinned to known arithmetic
# ---------------------------------------------------------------------------


def test_compute_cohen_kappa_intermediate_value_2x2_confusion() -> None:
    """Pin κ=0.5 on an 8-sample 2-bin confusion matrix [[3,1],[1,3]].

    bins=2 → cutoffs ``[0.5]``; bin 0 = ``[0, 0.5)``, bin 1 = ``[0.5, 1]``.

    Construct:
      - 3 samples both-bin-0 (h=0.2, j=0.2)
      - 3 samples both-bin-1 (h=0.8, j=0.8)
      - 1 sample h=0.2 / j=0.8  (h-bin-0, j-bin-1)
      - 1 sample h=0.8 / j=0.2  (h-bin-1, j-bin-0)

    Confusion matrix (rows = human, cols = judge)::

           j0  j1
        h0  3   1     row sum 4
        h1  1   3     row sum 4
            4   4

    po = (3+3)/8 = 0.75
    pe = (row0*col0 + row1*col1) / N² = (4*4 + 4*4) / 64 = 32/64 = 0.5
    κ  = (po - pe) / (1 - pe) = 0.25 / 0.5 = 0.5

    This catches swapped row/col marginals (symmetric here, so undetectable
    — but combined with R1's asymmetric per-axis test below it pins both
    failure modes). It also catches population vs sample variance bugs
    (would give κ ≠ 0.5).
    """
    human = [0.2, 0.2, 0.2, 0.8, 0.8, 0.8, 0.2, 0.8]
    judge = [0.2, 0.2, 0.2, 0.8, 0.8, 0.8, 0.8, 0.2]
    assert compute_cohen_kappa(human, judge, bins=2) == pytest.approx(0.5, abs=1e-9)


# ---------------------------------------------------------------------------
# Y1 — per-axis disagreement is genuinely independent
# ---------------------------------------------------------------------------


def test_calibrate_per_axis_kappa_independent() -> None:
    """Force getattr(js, axis) to actually vary by axis.

    Process and output axes track human perfectly (κ=1.0); token axis is
    anti-correlated (κ=-1.0). A typo like always reading ``js.process``
    inside the per-axis loop would silently return κ=1.0 on every axis and
    fail this test.
    """
    # 4 records: human/judge agree on process+output, disagree (anti) on token
    records = [
        _mk_record("r1", 0.1, 0.1, 0.1),
        _mk_record("r2", 0.9, 0.9, 0.9),
        _mk_record("r3", 0.1, 0.1, 0.1),
        _mk_record("r4", 0.9, 0.9, 0.9),
    ]
    pool = _StubPool(
        canned={
            "r1": _mk_score(0.1, 0.1, 0.9),  # token flipped
            "r2": _mk_score(0.9, 0.9, 0.1),  # token flipped
            "r3": _mk_score(0.1, 0.1, 0.9),
            "r4": _mk_score(0.9, 0.9, 0.1),
        }
    )
    report = calibrate(records, pool)
    assert report.kappa_per_axis["process"] == pytest.approx(1.0, abs=1e-9)
    assert report.kappa_per_axis["output"] == pytest.approx(1.0, abs=1e-9)
    # Token: h_bins=[0,2,0,2], j_bins=[2,0,2,0] → κ = -1.0 (same derivation
    # as test_kappa_random_agreement_is_zero_or_negative).
    assert report.kappa_per_axis["token"] == pytest.approx(-1.0, abs=1e-9)
    # kappa_mean = (1 + 1 + (-1)) / 3 = 1/3 ≈ 0.333… < 0.6 → verdict=False
    assert report.kappa_mean == pytest.approx(1.0 / 3.0, abs=1e-9)
    assert report.passed is False


# ---------------------------------------------------------------------------
# Y2 — bins != 3 coverage (lock the i/bins fallback)
# ---------------------------------------------------------------------------


def test_bin_cutoffs_pinned_for_bins_3() -> None:
    # Spec §7.2 / decision #124 — LITERAL truncated decimals, not 1/3, 2/3.
    assert _bin_cutoffs(3) == [0.33, 0.66]


def test_bin_cutoffs_fallback_for_bins_4() -> None:
    # bins != 3 → equal-width ``i / bins`` fallback.
    assert _bin_cutoffs(4) == [0.25, 0.5, 0.75]


def test_bin_cutoffs_fallback_for_bins_2() -> None:
    assert _bin_cutoffs(2) == [0.5]


def test_compute_cohen_kappa_bins_4_smoke() -> None:
    """Exercise the bins=4 fallback path end-to-end through κ.

    Four samples one per bin (0.1→0, 0.4→1, 0.6→2, 0.9→3); perfect agreement
    → κ=1.0. Confirms the fallback cutoffs ``[0.25, 0.5, 0.75]`` produce
    distinct bins and the κ math works for bins != 3.
    """
    human = [0.1, 0.4, 0.6, 0.9]
    judge = [0.1, 0.4, 0.6, 0.9]
    assert compute_cohen_kappa(human, judge, bins=4) == pytest.approx(1.0, abs=1e-9)
