"""Content that arrives as a list must still reach the surface.

A run produced ten exam questions as a JSON array. The object parser rejected
the array, `structured` came back null, and the questions went into `text` as a
serialised string. The harness exposed that string at `/summary`, the surface
bound to `/summary/0/question_text`, and a JSON pointer cannot index into a
string. Fifty-five components validated, rendered, and showed nothing.

Nothing in that chain reported an error, which is what makes it worth a test.
"""
from __future__ import annotations

import json

from sourcecode.runtime import _as_section, _parse_json_array


QUESTIONS = [
    {"id": "Q1", "stem": "A solid sphere rolls without slipping. Its acceleration is:",
     "options": ["A) (5/7)g", "B) (2/3)g", "C) (3/5)g", "D) (7/5)g"],
     "correct_answer": "A", "solution": "Use I = (2/5)MR^2 and a = R alpha."},
    {"id": "Q2", "stem": "The derivative of ln(sec x) is:",
     "options": ["A) tan x", "B) cot x", "C) sec x", "D) csc x"],
     "correct_answer": "A", "solution": "d/dx ln(sec x) = tan x."},
]


def test_a_bare_json_array_is_read_rather_than_discarded() -> None:
    items = _parse_json_array(json.dumps(QUESTIONS))
    assert items is not None and len(items) == 2


def test_a_fenced_array_is_read_too() -> None:
    assert _parse_json_array("```json\n" + json.dumps(QUESTIONS) + "\n```") is not None


def test_an_item_folds_into_heading_points_and_detail() -> None:
    section = _as_section(QUESTIONS[0])
    assert section["heading"].startswith("A solid sphere")
    assert section["points"] == QUESTIONS[0]["options"]
    assert "I = (2/5)MR^2" in section["detail"]


def test_nothing_the_model_wrote_is_silently_dropped() -> None:
    """Fields the three slots do not claim still reach the detail."""
    section = _as_section(QUESTIONS[0])
    assert "correct_answer: A" in section["detail"]
    assert "id: Q1" in section["detail"]


def test_the_mapping_is_about_item_shape_not_about_quizzes() -> None:
    """The same three slots have to fit content that is not an exam at all."""
    faq = _as_section({"question": "Why is the deploy slow?",
                       "answer": "The image is rebuilt on the host."})
    assert faq["heading"] == "Why is the deploy slow?"
    assert "rebuilt on the host" in faq["detail"]

    step = _as_section({"title": "Install", "steps": ["clone", "uv sync"],
                        "description": "Takes about a minute."})
    assert step["heading"] == "Install"
    assert step["points"] == ["clone", "uv sync"]
    assert "about a minute" in step["detail"]


def test_a_scalar_where_a_list_belongs_does_not_break_it() -> None:
    section = _as_section({"stem": "One thing", "options": "only one", "solution": "s"})
    assert section["points"] == ["only one"]


def test_an_array_of_scalars_is_not_treated_as_sections() -> None:
    """Only a list of objects is a list of items; a list of strings is not."""
    items = _parse_json_array('["alpha", "beta"]')
    assert items == ["alpha", "beta"]
    assert not all(isinstance(i, dict) for i in items)


def test_prose_is_still_not_an_array() -> None:
    assert _parse_json_array("Here are some questions, in no particular order.") is None
