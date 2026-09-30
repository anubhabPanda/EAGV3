from proofs.channel_prompts import (
    REQUIRE_PARALLEL,
    REQUIRE_WAIT_RESUME,
    REQUIRED_TOOL_GROUPS,
    SCENARIOS,
)


def test_twenty_unique_real_channel_scenarios_cover_the_installed_catalogue():
    installed = {
        "discord", "gmail", "imap", "line", "local_mic", "matrix", "signal", "slack",
        "teams", "telegram", "twilio_sms", "twilio_voice", "webhook", "webui", "whatsapp",
    }
    assert len(SCENARIOS) == 20
    assert len({scenario.id for scenario in SCENARIOS}) == 20
    assert {scenario.channel for scenario in SCENARIOS} == installed
    assert all(len(scenario.prompt) >= 100 for scenario in SCENARIOS)
    assert all(scenario.why_agentic and scenario.likely_tools for scenario in SCENARIOS)
    assert set(REQUIRED_TOOL_GROUPS) == {scenario.id for scenario in SCENARIOS}
    assert REQUIRE_PARALLEL | REQUIRE_WAIT_RESUME <= set(REQUIRED_TOOL_GROUPS)


def test_scenarios_are_proof_data_not_benchmark_phrases_in_agent_code():
    # Exact expected plans are deliberately absent. A future model may choose a
    # better valid graph; the proof records what it actually did.
    assert all("must call" not in scenario.prompt.lower() for scenario in SCENARIOS)
    assert sum(scenario.follow_up is not None for scenario in SCENARIOS) == 1
