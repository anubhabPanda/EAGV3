"""Labelled prompt pairs, and the threshold arithmetic they support.

A semantic cache is a classifier. It is handed two prompts and it decides, from
one number, whether they want the same answer. Every classifier has an operating
point, and the operating point of a semantic cache is its similarity threshold —
so the only honest way to choose one is the way any operating point is chosen:
label some pairs by hand, score them with the real scorer, and sweep.

This module owns the two halves of that and nothing else:

* :func:`load_pairs` reads the labelled set. The pairs are DATA, in a file the
  reviewer owns, for the same reason the task set in :mod:`sourcecode.evals.tasks`
  is: a set of "these two mean the same thing" judgements compiled into Python
  is a use case welded into a library, and it measures nothing anyone else can
  reuse.
* :func:`sweep` turns scores plus labels into a true-positive and
  false-positive rate at each candidate threshold. It knows nothing about
  embeddings, cosine, caches or gateways — it takes floats and booleans — so the
  same function grades any scorer you point at the same file.

The asymmetry between the two error kinds is the whole reason this exists. A
false negative costs one provider call. A false positive returns a stored answer
to a question nobody asked, with no signal that anything went wrong.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Sequence

import yaml

#: Fields the loader understands. Anything else a record carries is preserved in
#: :attr:`LabelledPair.metadata`, so a richer pair file loses nothing.
KNOWN_FIELDS = ("id", "a", "b", "label", "family", "note")

#: The label meaning "these two want the same answer". Every other label is a
#: negative, so a file may distinguish as many kinds of negative as it likes
#: without the arithmetic having to learn any of them.
POSITIVE_LABEL = "same"


@dataclass(frozen=True)
class LabelledPair:
    """Two prompts and a human's verdict on whether they want one answer."""

    id: str
    a: str
    b: str
    label: str
    family: str | None = None
    note: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def positive(self) -> bool:
        """True when a cache SHOULD serve b from a's stored response."""
        return self.label.strip().lower() == POSITIVE_LABEL

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "a": self.a,
            "b": self.b,
            "label": self.label,
            "family": self.family,
            "note": self.note,
            "metadata": dict(self.metadata),
        }


def _record_to_pair(record: Any, ordinal: int, origin: str) -> LabelledPair:
    if not isinstance(record, dict):
        raise ValueError(f"{origin}: record {ordinal} is not a mapping")
    a, b = str(record.get("a") or "").strip(), str(record.get("b") or "").strip()
    if not a or not b:
        raise ValueError(f"{origin}: record {ordinal} needs non-empty 'a' and 'b'")
    label = str(record.get("label") or "").strip()
    if not label:
        raise ValueError(f"{origin}: record {ordinal} has no 'label'; a pair with no ground truth "
                         f"cannot be scored (use '{POSITIVE_LABEL}' or any other word for a negative)")
    return LabelledPair(
        id=str(record.get("id") or f"pair_{ordinal:03d}"),
        a=a,
        b=b,
        label=label,
        family=str(record["family"]).strip() if record.get("family") is not None else None,
        note=str(record["note"]).strip() if record.get("note") is not None else None,
        metadata={key: value for key, value in record.items() if key not in KNOWN_FIELDS},
    )


def _records(path: Path) -> Iterable[Any]:
    """Every record in the file, whatever container the file chose."""
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() in {".jsonl", ".ndjson"}:
        for line in text.splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            try:
                yield json.loads(stripped)
            except json.JSONDecodeError as error:
                raise ValueError(f"{path}: not valid JSON Lines: {error}") from error
        return
    loaded = yaml.safe_load(text) if path.suffix.lower() in {".yaml", ".yml"} else json.loads(text)
    if isinstance(loaded, dict):
        loaded = loaded.get("pairs")
    if not isinstance(loaded, list):
        raise ValueError(f"{path}: expected a list of pairs, or a mapping with a 'pairs' list")
    yield from loaded


def load_pairs(path: str | Path) -> tuple[LabelledPair, ...]:
    """Load a labelled pair set. Raises rather than silently dropping records."""
    resolved = Path(path).expanduser()
    if not resolved.exists():
        raise FileNotFoundError(f"pair file not found: {resolved}")
    pairs = tuple(
        _record_to_pair(record, ordinal, str(resolved))
        for ordinal, record in enumerate(_records(resolved), start=1)
    )
    if not pairs:
        raise ValueError(f"{resolved}: no pairs found")
    ids = [pair.id for pair in pairs]
    duplicates = sorted({identifier for identifier in ids if ids.count(identifier) > 1})
    if duplicates:
        raise ValueError(f"{resolved}: duplicate pair ids {duplicates}")
    if not any(pair.positive for pair in pairs):
        raise ValueError(f"{resolved}: no '{POSITIVE_LABEL}' pairs; a sweep with no positives "
                         f"has no true-positive rate to report")
    if all(pair.positive for pair in pairs):
        raise ValueError(f"{resolved}: every pair is '{POSITIVE_LABEL}'; with no negatives the "
                         f"false-positive rate is undefined and any threshold looks safe")
    return pairs


def by_family(pairs: Iterable[LabelledPair]) -> dict[str, list[str]]:
    """Pair ids grouped by their self-declared family label, for the report."""
    grouped: dict[str, list[str]] = {}
    for pair in pairs:
        grouped.setdefault(pair.family or "unlabelled", []).append(pair.id)
    return grouped


# --------------------------------------------------------------------------- #
# the sweep
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class Operating:
    """What a threshold does to a labelled set: the confusion matrix and its rates."""

    threshold: float
    true_positives: int
    false_negatives: int
    false_positives: int
    true_negatives: int

    @property
    def positives(self) -> int:
        return self.true_positives + self.false_negatives

    @property
    def negatives(self) -> int:
        return self.false_positives + self.true_negatives

    @property
    def tpr(self) -> float:
        """Of the pairs that SHOULD hit, the fraction that do. The saving."""
        return self.true_positives / self.positives if self.positives else 0.0

    @property
    def fpr(self) -> float:
        """Of the pairs that MUST NOT hit, the fraction that do. The wrong answers."""
        return self.false_positives / self.negatives if self.negatives else 0.0

    def as_dict(self) -> dict[str, Any]:
        return {
            "threshold": round(self.threshold, 4),
            "true_positives": self.true_positives,
            "false_negatives": self.false_negatives,
            "false_positives": self.false_positives,
            "true_negatives": self.true_negatives,
            "tpr": round(self.tpr, 4),
            "fpr": round(self.fpr, 4),
        }


def thresholds(low: float, high: float, step: float) -> tuple[float, ...]:
    """The grid to sweep, from ``low`` up to ``high`` and never past it.

    Values are rounded to kill float drift, and the step count is floored with a
    tolerance rather than rounded: ``0.70..0.99`` by ``0.05`` must stop at 0.95,
    not run on to 1.00, because a threshold outside the range the caller asked
    about is a row nobody can interpret.
    """
    if step <= 0:
        raise ValueError("threshold step must be positive")
    if high < low:
        raise ValueError(f"threshold range {low}..{high} is empty")
    count = int(math.floor((high - low) / step + 1e-9))
    return tuple(round(low + index * step, 6) for index in range(count + 1))


def sweep(
    scored: Sequence[tuple[LabelledPair, float]],
    grid: Sequence[float],
) -> tuple[Operating, ...]:
    """The confusion matrix at every threshold in ``grid``.

    ``scored`` is (pair, similarity). A pair "hits" at threshold ``t`` when its
    similarity is >= ``t``, which is exactly the comparison the cache makes.
    """
    out = []
    for threshold in grid:
        tp = fn = fp = tn = 0
        for pair, score in scored:
            hit = score >= threshold
            if pair.positive:
                tp, fn = (tp + 1, fn) if hit else (tp, fn + 1)
            else:
                fp, tn = (fp + 1, tn) if hit else (fp, tn + 1)
        out.append(Operating(threshold, tp, fn, fp, tn))
    return tuple(out)


def separable(scored: Sequence[tuple[LabelledPair, float]]) -> dict[str, Any]:
    """Is there ANY threshold that admits every positive and no negative?

    This is the question a threshold recommendation is really answering, and it
    has a one-line answer: the lowest-scoring positive must outscore the
    highest-scoring negative. When it does not, no operating point is safe and a
    proof that only reports a hit rate is hiding the collisions.
    """
    positives = [score for pair, score in scored if pair.positive]
    negatives = [(pair, score) for pair, score in scored if not pair.positive]
    if not positives or not negatives:
        return {"separable": False, "reason": "need both positive and negative pairs"}
    worst_positive = min(positives)
    dearest = max(negatives, key=lambda item: item[1])
    return {
        "separable": worst_positive > dearest[1],
        "lowest_positive": round(worst_positive, 6),
        "highest_negative": round(dearest[1], 6),
        "highest_negative_id": dearest[0].id,
        "highest_negative_family": dearest[0].family,
        "margin": round(worst_positive - dearest[1], 6),
    }


def steepest_fpr_drop(operating: Sequence[Operating]) -> dict[str, Any]:
    """Where in the range the collision rate changes most, and by how much.

    A claim of the form "below X collisions become common" is a claim about a
    KNEE in this curve. Rather than testing an inherited X, this finds the X the
    data itself puts the knee at: the adjacent pair of thresholds across which
    the false-positive rate falls furthest. Ties go to the lower threshold, so
    the answer is the first place the curve turns.
    """
    steps = [
        (below, above, below.fpr - above.fpr)
        for below, above in zip(operating, operating[1:])
    ]
    if not steps:
        return {"measured": False, "reason": "a sweep of fewer than two thresholds has no knee"}
    below, above, drop = max(steps, key=lambda step: (step[2], -step[0].threshold))
    return {
        "measured": True,
        "knee_at": above.threshold,
        "fpr_below": round(below.fpr, 4),
        "fpr_at": round(above.fpr, 4),
        "drop": round(drop, 4),
        "collisions_below": below.false_positives,
        "collisions_at": above.false_positives,
        "negatives": above.negatives,
        "flat": drop <= 0.0,
    }


def best_operating(operating: Sequence[Operating]) -> Operating | None:
    """The safest useful point: among thresholds with no false positive, the
    one that catches the most paraphrases.

    Ties break upward, towards the stricter threshold: when two thresholds catch
    the same paraphrases and admit the same nothing, the higher one has more
    room before the next unlabelled negative walks in.

    When nothing achieves zero false positives the same rule is applied to the
    whole range, which returns the least-bad point rather than a safe one. The
    caller must read :attr:`Operating.false_positives` before calling the result
    a recommendation, because "there is no safe threshold" is itself the finding.
    """
    if not operating:
        return None
    clean = [point for point in operating if point.false_positives == 0]
    pool = clean or operating
    return max(pool, key=lambda point: (point.tpr, -point.fpr, point.threshold))
