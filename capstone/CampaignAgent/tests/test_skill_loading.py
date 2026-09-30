"""Skills are requested, not matched: the planner reads a listing and asks by name.

The earlier design injected whole skill bodies whenever the run's opening prompt
happened to contain a keyword. A skill could therefore never fire because the
agent decided it needed one, which is the only reason to have skills at all.
These tests hold the three levels of disclosure apart: a listing that is always
carried, a body that arrives on request, and reference files that arrive only if
the body sends the agent to them.
"""
from __future__ import annotations

import textwrap

import pytest

from sourcecode.capabilities import default_registry
from sourcecode.planner import GeneralAgentPlanner
from sourcecode.skills import GenericSkill, SkillError, SkillManager


def write(tmp_path, folder: str, text: str, refs: dict[str, str] | None = None):
    d = tmp_path / folder
    d.mkdir(parents=True, exist_ok=True)
    (d / "SKILL.md").write_text(textwrap.dedent(text).lstrip(), encoding="utf-8")
    for name, body in (refs or {}).items():
        r = d / "references"
        r.mkdir(exist_ok=True)
        (r / name).write_text(body, encoding="utf-8")
    return d / "SKILL.md"


BIG = """
    ---
    name: bigskill
    description: This skill should be used when the task involves widgets.
    when_to_use: a widget is being built
    keywords: [widget]
    ---
    THE-BODY-MARKER. Detailed widget instructions go here.
"""

ALWAYS = """
    ---
    name: house
    description: Always on.
    always: true
    ---
    HOUSE-MARKER. Small commits.
"""


@pytest.fixture()
def manager(tmp_path):
    write(tmp_path, "bigskill", BIG, refs={"deep.md": "DEEP-MARKER. The long tables."})
    write(tmp_path, "house", ALWAYS)
    return SkillManager.discover(tmp_path)


async def _llm(prompt: str, system: str) -> dict:  # pragma: no cover - not called
    return {"text": "{}"}


# -- level one: the listing ----------------------------------------------


def test_the_listing_carries_routing_lines_and_never_a_body(manager) -> None:
    rows = manager.listing()
    assert [r["name"] for r in rows] == ["bigskill"], "an always-on skill needs no routing line"
    assert "widget" in rows[0]["description"]
    assert "THE-BODY-MARKER" not in str(rows), "the listing must not carry instructions"


def test_the_planner_is_shown_the_listing(manager) -> None:
    import json

    from sourcecode.core.live_graph import Event, GraphSnapshot

    planner = GeneralAgentPlanner(_llm, default_registry(), goal="do a thing", skills=manager)
    graph = GraphSnapshot(run_id="r", finished=False, nodes={}, edges=[])
    event = Event(kind="run_started", node_id=None, payload={}, sequence=1,
                  recorded_at="2026-08-11T00:00:00+00:00")
    payload = json.loads(planner._prompt(graph, event))

    assert [s["name"] for s in payload["skills_available"]] == ["bigskill"]
    assert "THE-BODY-MARKER" not in json.dumps(payload)
    assert any(c["name"] == "load_skill" for c in payload["capabilities"]), \
        "the planner must be able to act on the listing it was shown"


def test_a_body_is_absent_until_it_is_requested(manager) -> None:
    planner = GeneralAgentPlanner(_llm, default_registry(), goal="build a thing", skills=manager)

    assert "THE-BODY-MARKER" not in planner._system(), "not asked for, must not be present"
    assert "HOUSE-MARKER" in planner._system(), "an always-on skill needs no request"

    planner._loaded = ["bigskill"]
    assert "THE-BODY-MARKER" in planner._system(), "requested, so present"


def test_a_loaded_skill_survives_for_the_rest_of_the_run(manager) -> None:
    """Derived from the graph, so a resumed run reloads what the journal says."""
    import asyncio

    from sourcecode.core.live_graph import Event, GraphSnapshot

    planner = GeneralAgentPlanner(_llm, default_registry(), goal="g", skills=manager)
    nodes = {"load_1": {"skill": "load_skill", "input": {"name": "bigskill"},
                        "state": "succeeded", "result": {}}}
    graph = GraphSnapshot(run_id="r", finished=False, nodes=nodes, edges=[])
    event = Event(kind="task_succeeded", node_id="load_1", payload={}, sequence=2,
                  recorded_at="2026-08-11T00:00:00+00:00")
    asyncio.run(planner.plan(graph, event))
    assert planner._loaded == ["bigskill"]
    assert "THE-BODY-MARKER" in planner._system()


def test_a_reference_fetch_does_not_count_as_loading_the_skill(manager) -> None:
    import asyncio

    from sourcecode.core.live_graph import Event, GraphSnapshot

    planner = GeneralAgentPlanner(_llm, default_registry(), goal="g", skills=manager)
    nodes = {"ref_1": {"skill": "load_skill",
                       "input": {"name": "bigskill", "reference": "deep.md"},
                       "state": "succeeded", "result": {}}}
    graph = GraphSnapshot(run_id="r", finished=False, nodes=nodes, edges=[])
    asyncio.run(planner.plan(graph, Event(kind="task_succeeded", node_id="ref_1", payload={},
                                          sequence=2, recorded_at="2026-08-11T00:00:00+00:00")))
    assert planner._loaded == []


# -- level three: references ---------------------------------------------


def test_references_are_listed_but_not_loaded(manager) -> None:
    assert manager.references("bigskill") == ["deep.md"]
    assert "DEEP-MARKER" not in manager.body("bigskill")
    assert "DEEP-MARKER" in manager.reference("bigskill", "deep.md")


@pytest.mark.parametrize("attack", [
    "../../../etc/passwd", "../SKILL.md", "../../house/SKILL.md",
    "/etc/passwd", "deep.md/../../SKILL.md",
])
def test_a_reference_cannot_escape_its_own_skill_directory(manager, attack: str) -> None:
    """A skill body is untrusted text. If it could name any path, the skills
    directory would be a file-read primitive pointed at the whole host."""
    with pytest.raises(SkillError, match="not a reference"):
        manager.reference("bigskill", attack)


def test_an_unknown_skill_or_reference_is_refused(manager) -> None:
    with pytest.raises(SkillError, match="no enabled skill"):
        manager.body("nosuch")
    with pytest.raises(SkillError, match="not a reference"):
        manager.reference("bigskill", "missing.md")


def test_a_disabled_skill_leaves_the_listing_and_refuses_to_load(manager) -> None:
    manager.disable("bigskill")
    assert manager.listing() == []
    with pytest.raises(SkillError, match="no enabled skill"):
        manager.body("bigskill")


# -- the cost argument ----------------------------------------------------


def test_the_listing_costs_far_less_than_the_bodies(tmp_path) -> None:
    """The whole point of disclosure: carrying twelve skills is nearly free."""
    for i in range(12):
        write(tmp_path, f"s{i}", f"""
            ---
            name: s{i}
            description: This skill should be used when the task is number {i}.
            keywords: [k{i}]
            ---
            """ + ("body text. " * 300))
    m = SkillManager.discover(tmp_path)
    listing = sum(len(str(r)) for r in m.listing())
    bodies = sum(len(m.body(s.name)) for s in m.all())
    assert len(m) == 12
    assert listing < bodies / 10, f"listing {listing} vs bodies {bodies}"


# -- the completeness review must not read a truncated outcome ------------


def test_the_evidence_review_sees_a_long_outcome_whole() -> None:
    """A real block: ten questions produced, six survived the clip, run refused.

    The default outcome clip is 4,000 characters, which is right for planning
    and wrong for judging completeness. The reviewer counted what was left and
    reported the work unfinished.
    """
    import json

    from sourcecode.core.live_graph import GraphSnapshot

    questions = "".join(
        f'{{"id":"Q{i}","stem":"{"physics question text " * 45}","options":["A","B","C","D"]}},'
        for i in range(1, 11)
    )
    assert len(questions) > 8_000

    planner = GeneralAgentPlanner(_llm, default_registry(), goal="ten questions")
    nodes = {"gen": {"skill": "content", "input": {}, "state": "succeeded",
                     "result": {"text": questions}}}
    graph = GraphSnapshot(run_id="r", finished=False, nodes=nodes, edges=[])

    plan_payload = json.loads(planner._prompt(graph, Event(
        kind="task_succeeded", node_id="gen", payload={}, sequence=2,
        recorded_at="2026-08-11T00:00:00+00:00")))
    review_payload = json.loads(planner._review_prompt(graph))

    # Count inside the outcome value itself: the payload is JSON, so the
    # question markers arrive escaped and cannot be counted in the dumped form.
    seen_planning = plan_payload["graph"]["nodes"][0]["outcome"]["text"].count('"stem"')
    seen_review = review_payload["completed_evidence"][0]["outcome"]["text"].count('"stem"')

    assert seen_planning < 10, "planning is allowed to work from a clipped outcome"
    assert seen_review == 10, (
        f"the completeness reviewer saw only {seen_review} of 10 questions; "
        "it will report finished work as incomplete"
    )


from sourcecode.core.live_graph import Event  # noqa: E402  (used above)


def test_a_requested_skill_is_never_dropped_by_the_budget(tmp_path) -> None:
    """It asked for it. Dropping it silently leaves the run believing it has
    guidance it never received, which is worse than any budget it could blow."""
    write(tmp_path, "house", ALWAYS)
    for i in range(3):
        write(tmp_path, f"big{i}", f"""
            ---
            name: big{i}
            description: This skill should be used for job {i}.
            keywords: [job]
            ---
            BIG{i}-MARKER. """ + ("filler " * 900))
    m = SkillManager.discover(tmp_path)

    rendered = m.render("a job", requested=["big2"])
    assert "BIG2-MARKER" in rendered, "the requested skill must survive"
    assert "HOUSE-MARKER" in rendered, "always-on must survive"
    # the keyword floor is what gets trimmed
    assert not ("BIG0-MARKER" in rendered and "BIG1-MARKER" in rendered)
