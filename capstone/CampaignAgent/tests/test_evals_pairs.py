"""Labelled pairs load as data, and the threshold sweep is arithmetic anyone
can check by hand.

p6 turns "below 0.92 collisions become common" from an inherited claim into a
measurement. That measurement is only worth something if the counting underneath
it is right, so the confusion matrix, the rates, the separability verdict and
the operating-point choice are all checked here on numbers small enough to
verify on paper — with no embedder, no gateway and no network in sight.
"""

from __future__ import annotations

import json

import pytest

from sourcecode.evals import (
    LabelledPair,
    best_operating,
    by_family,
    load_pairs,
    separable,
    steepest_fpr_drop,
    sweep,
    thresholds,
)
from sourcecode.evals.pairs import Operating

PROOF_PAIRS = "proofs/pairs/paraphrases.jsonl"


def _pair(identifier: str, label: str, family: str | None = None) -> LabelledPair:
    return LabelledPair(id=identifier, a="a", b="b", label=label, family=family)


def _write(tmp_path, name: str, text: str):
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


# ── loading ─────────────────────────────────────────────────────────────────


def test_the_shipped_pair_file_loads_and_is_labelled_both_ways():
    """The file p6 defaults to is the reviewer's entry point; it must parse."""
    pairs = load_pairs(PROOF_PAIRS)
    assert len(pairs) >= 4
    assert any(pair.positive for pair in pairs)
    assert any(not pair.positive for pair in pairs)
    assert all(pair.a and pair.b for pair in pairs)


def test_every_shipped_negative_declares_a_family():
    """The report separates hard negatives from easy ones, so the data has to."""
    families = by_family(load_pairs(PROOF_PAIRS))
    assert "unlabelled" not in families
    assert len(families) > 1


def test_jsonl_comments_and_blank_lines_are_skipped(tmp_path):
    path = _write(tmp_path, "p.jsonl", "\n".join([
        "# a comment explaining the file",
        "",
        json.dumps({"id": "x", "a": "one", "b": "uno", "label": "same"}),
        json.dumps({"id": "y", "a": "one", "b": "two", "label": "different"}),
    ]))
    pairs = load_pairs(path)
    assert [p.id for p in pairs] == ["x", "y"]
    assert pairs[0].positive and not pairs[1].positive


def test_json_and_yaml_containers_load_the_same_pairs(tmp_path):
    records = [
        {"id": "x", "a": "one", "b": "uno", "label": "same"},
        {"id": "y", "a": "one", "b": "two", "label": "different"},
    ]
    as_json = _write(tmp_path, "p.json", json.dumps({"pairs": records}))
    as_yaml = _write(tmp_path, "p.yaml", "pairs:\n" + "".join(
        f"  - {json.dumps(record)}\n" for record in records
    ))
    assert [p.id for p in load_pairs(as_json)] == [p.id for p in load_pairs(as_yaml)] == ["x", "y"]


def test_unknown_fields_survive_in_metadata(tmp_path):
    path = _write(tmp_path, "p.jsonl", "\n".join([
        json.dumps({"id": "x", "a": "1", "b": "2", "label": "same", "source": "ticket-914"}),
        json.dumps({"id": "y", "a": "1", "b": "3", "label": "different"}),
    ]))
    assert load_pairs(path)[0].metadata == {"source": "ticket-914"}


def test_any_word_other_than_same_is_a_negative(tmp_path):
    """A file may name as many kinds of negative as it likes."""
    path = _write(tmp_path, "p.jsonl", "\n".join([
        json.dumps({"id": "x", "a": "1", "b": "2", "label": "SAME"}),
        json.dumps({"id": "y", "a": "1", "b": "3", "label": "contradicts"}),
        json.dumps({"id": "z", "a": "1", "b": "4", "label": "unrelated"}),
    ]))
    assert [p.positive for p in load_pairs(path)] == [True, False, False]


@pytest.mark.parametrize("records, message", [
    ([{"id": "x", "a": "1", "b": "2"}], "no 'label'"),
    ([{"id": "x", "a": "", "b": "2", "label": "same"}], "non-empty"),
    ([{"id": "x", "a": "1", "b": "2", "label": "same"},
      {"id": "x", "a": "3", "b": "4", "label": "different"}], "duplicate"),
    ([{"id": "x", "a": "1", "b": "2", "label": "different"}], "no 'same' pairs"),
    ([{"id": "x", "a": "1", "b": "2", "label": "same"}], "every pair is 'same'"),
])
def test_a_bad_pair_file_raises_rather_than_measuring_nonsense(tmp_path, records, message):
    """Silently dropping a record would move TPR and FPR with no warning."""
    path = _write(tmp_path, "p.jsonl", "\n".join(json.dumps(r) for r in records))
    with pytest.raises((ValueError, KeyError)) as caught:
        load_pairs(path)
    assert message in str(caught.value)


def test_a_missing_file_names_itself(tmp_path):
    with pytest.raises(FileNotFoundError, match="pair file not found"):
        load_pairs(tmp_path / "nope.jsonl")


# ── the grid ────────────────────────────────────────────────────────────────


def test_the_grid_is_inclusive_at_both_ends_and_free_of_float_drift():
    grid = thresholds(0.85, 0.99, 0.01)
    assert grid[0] == 0.85 and grid[-1] == 0.99 and len(grid) == 15
    assert all(round(value, 2) == value for value in grid)


def test_the_grid_never_runs_past_the_high_end():
    """0.70..0.99 by 0.05 stops at 0.95. A row at 1.00 is outside what was asked."""
    grid = thresholds(0.70, 0.99, 0.05)
    assert grid[-1] == 0.95
    assert 1.0 not in grid


def test_a_range_narrower_than_one_step_is_a_single_threshold():
    assert thresholds(0.95, 0.96, 0.05) == (0.95,)
    assert thresholds(0.95, 0.95, 0.01) == (0.95,)


@pytest.mark.parametrize("low, high, step", [(0.9, 0.8, 0.01), (0.8, 0.9, 0.0), (0.8, 0.9, -0.1)])
def test_an_impossible_grid_raises(low, high, step):
    with pytest.raises(ValueError):
        thresholds(low, high, step)


# ── the sweep ───────────────────────────────────────────────────────────────


def test_the_confusion_matrix_is_countable_by_hand():
    """Two positives at 0.96/0.90 and two negatives at 0.97/0.80, swept at 0.95.

    A hit is ``score >= threshold`` — the same comparison the cache makes — so
    at 0.95 exactly one positive and one negative are admitted.
    """
    scored = [
        (_pair("p1", "same"), 0.96),
        (_pair("p2", "same"), 0.90),
        (_pair("n1", "different"), 0.97),
        (_pair("n2", "different"), 0.80),
    ]
    point = sweep(scored, [0.95])[0]
    assert (point.true_positives, point.false_negatives) == (1, 1)
    assert (point.false_positives, point.true_negatives) == (1, 1)
    assert point.tpr == 0.5 and point.fpr == 0.5


def test_the_threshold_comparison_is_inclusive():
    """A score exactly at the threshold hits, because ``>=`` is what ships."""
    scored = [(_pair("p1", "same"), 0.95), (_pair("n1", "different"), 0.94)]
    assert sweep(scored, [0.95])[0].true_positives == 1
    assert sweep(scored, [0.95])[0].false_positives == 0


def test_raising_the_threshold_never_raises_either_rate():
    scored = [(_pair(f"p{i}", "same"), 0.90 + i / 100) for i in range(5)]
    scored += [(_pair(f"n{i}", "different"), 0.88 + i / 100) for i in range(5)]
    points = sweep(scored, thresholds(0.85, 0.99, 0.01))
    assert all(b.tpr <= a.tpr and b.fpr <= a.fpr for a, b in zip(points, points[1:]))
    assert all(p.positives + p.negatives == len(scored) for p in points)


def test_every_pair_is_counted_exactly_once_at_every_threshold():
    scored = [(_pair(f"p{i}", "same" if i % 3 else "different"), i / 20) for i in range(20)]
    for point in sweep(scored, thresholds(0.0, 1.0, 0.1)):
        total = (point.true_positives + point.false_negatives
                 + point.false_positives + point.true_negatives)
        assert total == len(scored)


def test_rates_are_zero_rather_than_undefined_when_a_class_is_empty():
    point = Operating(0.9, true_positives=0, false_negatives=0, false_positives=1, true_negatives=0)
    assert point.tpr == 0.0 and point.fpr == 1.0


# ── separability, which is the question a threshold actually answers ────────


def test_a_separable_set_reports_the_gap_between_the_classes():
    scored = [
        (_pair("p1", "same"), 0.96), (_pair("p2", "same"), 0.94),
        (_pair("n1", "different"), 0.90), (_pair("n2", "different"), 0.40),
    ]
    verdict = separable(scored)
    assert verdict["separable"] is True
    assert verdict["lowest_positive"] == 0.94
    assert verdict["highest_negative"] == 0.90
    assert verdict["margin"] == pytest.approx(0.04)


def test_an_overlapping_set_names_the_negative_that_ruins_it():
    """The interesting case, and the one the real embeddings produce."""
    scored = [
        (_pair("p1", "same"), 0.94),
        (_pair("n1", "different", "near_miss"), 0.99),
        (_pair("n2", "different", "unrelated"), 0.20),
    ]
    verdict = separable(scored)
    assert verdict["separable"] is False
    assert verdict["highest_negative_id"] == "n1"
    assert verdict["highest_negative_family"] == "near_miss"
    assert verdict["margin"] < 0


# ── the measured danger line ────────────────────────────────────────────────


def test_the_knee_is_found_where_the_collisions_actually_stop():
    """Four negatives bunched just under 0.92 put the knee at 0.92.

    This is how a claim of the form "below X collisions become common" gets
    tested rather than repeated: X is read off the curve, not asserted.
    """
    scored = [(_pair("p1", "same"), 0.99)]
    scored += [(_pair(f"n{i}", "different"), 0.915) for i in range(4)]
    scored += [(_pair("n9", "different"), 0.999)]
    knee = steepest_fpr_drop(sweep(scored, thresholds(0.85, 0.99, 0.01)))
    assert knee["measured"] is True
    assert knee["knee_at"] == pytest.approx(0.92)
    assert (knee["collisions_below"], knee["collisions_at"]) == (5, 1)
    assert knee["flat"] is False


def test_a_curve_with_no_knee_reports_that_it_is_flat():
    """No negative in the range means nothing to fall, and no danger line."""
    scored = [(_pair("p1", "same"), 0.99), (_pair("n1", "different"), 0.10)]
    knee = steepest_fpr_drop(sweep(scored, thresholds(0.85, 0.99, 0.01)))
    assert knee["flat"] is True and knee["drop"] == 0.0


def test_a_knee_needs_at_least_two_thresholds():
    scored = [(_pair("p1", "same"), 0.99), (_pair("n1", "different"), 0.10)]
    assert steepest_fpr_drop(sweep(scored, [0.95]))["measured"] is False


# ── choosing an operating point ─────────────────────────────────────────────


def test_the_chosen_point_prefers_zero_collisions_over_a_higher_hit_rate():
    """A negative at 0.95 sits between two positives at 0.99 and 0.93.

    Admitting the 0.93 paraphrase means admitting the 0.95 collision, so the
    safe answer gives up half the hit rate.
    """
    scored = [
        (_pair("p1", "same"), 0.99), (_pair("p2", "same"), 0.93),
        (_pair("n1", "different"), 0.95),
    ]
    point = best_operating(sweep(scored, thresholds(0.90, 0.99, 0.01)))
    assert point.false_positives == 0
    assert point.tpr == 0.5  # the 0.93 paraphrase is given up to stay safe


def test_ties_break_towards_the_stricter_threshold():
    """0.96 through 0.99 all catch the one positive and admit nothing.

    The highest is returned: equally effective, and further from the next
    negative that the labelled set has not seen yet.
    """
    scored = [(_pair("p1", "same"), 0.99), (_pair("n1", "different"), 0.95)]
    point = best_operating(sweep(scored, thresholds(0.90, 0.99, 0.01)))
    assert point.false_positives == 0
    assert point.threshold == pytest.approx(0.99)


def test_when_nothing_is_collision_free_the_least_bad_point_is_returned():
    """`best_operating` must still answer, so the caller can print that there
    is no safe threshold instead of crashing on ``None``."""
    scored = [(_pair("p1", "same"), 0.91), (_pair("n1", "different"), 0.99)]
    points = sweep(scored, thresholds(0.90, 0.99, 0.01))
    point = best_operating(points)
    assert point is not None and point.false_positives > 0


def test_no_thresholds_means_no_point():
    assert best_operating([]) is None


def test_an_operating_point_serialises_every_cell_and_both_rates():
    point = Operating(0.95, 3, 1, 2, 4)
    assert point.as_dict() == {
        "threshold": 0.95, "true_positives": 3, "false_negatives": 1,
        "false_positives": 2, "true_negatives": 4, "tpr": 0.75, "fpr": 0.3333,
    }
