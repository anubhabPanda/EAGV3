"""Twenty human prompts used to stress the channel-connected general agent.

These are proof inputs, never planner instructions.  The harness is expected to
choose capabilities from their advertised contracts and may produce a different
valid graph as models improve.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ChannelScenario:
    id: str
    channel: str
    prompt: str
    why_agentic: str
    likely_tools: tuple[str, ...]
    follow_up: str | None = None


SCENARIOS = (
    ChannelScenario(
        "travel_weather", "telegram",
        "I land in Bengaluru tomorrow at 7:00 AM and have six free hours. Check the current forecast "
        "and the official opening hours of Lalbagh and the Visvesvaraya museum, then give me a timed plan "
        "with a rain-safe fallback. Cite the pages you used.",
        "Resolves a relative date, gathers changing facts from independent sources, then synthesizes a plan.",
        ("current_datetime", "researcher", "fetch_url", "answer_with_evidence"),
    ),
    ChannelScenario(
        "remember_preference", "whatsapp",
        "Remember this for future recommendations: I am vegetarian, I am allergic to peanuts, and I prefer "
        "places reachable by metro. Store only those durable preferences and tell me exactly what you saved.",
        "Promotes an explicit user instruction into scoped durable memory.",
        ("remember_explicit_fact", "answer_with_evidence"),
    ),
    ChannelScenario(
        "security_mail", "gmail",
        "Our team received a warning that the latest requests Python package release may be compromised. "
        "Verify the claim against PyPI, the project's official repository, and a primary security advisory. "
        "Reply with what is known, what is not known, and the safest immediate action.",
        "Fact-checks a time-sensitive security claim using multiple primary sources.",
        ("researcher", "fetch_url", "coder_validator", "answer_with_evidence"),
    ),
    ChannelScenario(
        "platform_comparison", "slack",
        "Compare the current free tiers of Cloudflare Workers and Vercel Functions for a small Python API. "
        "Use only their official documentation, separate hard limits from pricing assumptions, and recommend "
        "one for 50,000 short requests per month in this thread.",
        "Parallel research must be reconciled into a decision under an explicit workload.",
        ("researcher", "calculate", "coder_validator", "answer_with_evidence"),
    ),
    ChannelScenario(
        "csv_grading", "teams",
        "Join sandbox files students.csv and submissions.csv by student_id. Report who has no submission, "
        "the average score by cohort, and any duplicate submission IDs. Do the aggregation with one read-only "
        "query and explain the result.",
        "Discovers structured evidence and performs a real multi-table query before explaining it.",
        ("query_csv", "answer_with_evidence"),
    ),
    ChannelScenario(
        "python_free_threading", "discord",
        "Is free-threaded Python ready for a production web service in the current stable Python release? "
        "Check the official Python documentation, the relevant PEP, and one major web framework's official "
        "position. Give me a go/no-go decision and the experiment I should run first.",
        "Requires current, source-grounded technical research and a qualified decision.",
        ("researcher", "fetch_url", "distiller", "answer_with_evidence"),
    ),
    ChannelScenario(
        "a2a_transport", "matrix",
        "Using the current official A2A specification, compare JSON-RPC over HTTP, streaming, push "
        "notifications, and gRPC. Build a compact decision table for an agent that may remain offline for "
        "hours, and cite the exact specification pages.",
        "Collects several protocol facts and converts them into a constraint-driven decision table.",
        ("researcher", "fetch_url", "distiller", "answer_with_evidence"),
    ),
    ChannelScenario(
        "viral_claim", "signal",
        "A forwarded message claims that India has made all AI-generated content illegal from this month. "
        "Check current primary government or statutory sources, distinguish a proposal from enacted law, and "
        "write a careful fact-check I can forward without amplifying the rumour.",
        "Evaluates a high-risk changing claim and must preserve uncertainty and source authority.",
        ("researcher", "fetch_url", "coder_validator", "answer_with_evidence"),
    ),
    ChannelScenario(
        "calendar_artifacts", "line",
        "Create calendar files for the three EAG review sessions on 18 August 2026, 25 August 2026, and "
        "1 September 2026. Use the title 'EAG review', verify every generated file, and return the artifact paths.",
        "Creates multiple side-effecting artifacts and verifies their deterministic outputs.",
        ("create_calendar_events", "verify_artifact", "answer_with_evidence"),
    ),
    ChannelScenario(
        "airport_brief", "twilio_sms",
        "I am at Delhi airport and can read only one SMS. Check today's Delhi weather and any current official "
        "airport disruption notice, then reply in at most 320 characters with the one action I should take.",
        "Combines live sources and strict delivery-channel length constraints.",
        ("current_datetime", "researcher", "answer_with_evidence"),
    ),
    ChannelScenario(
        "voice_briefing", "twilio_voice",
        "Give me a spoken-style briefing of the three most consequential AI lab announcements published in the "
        "last 30 days. Verify each against the lab's own publication, state its publication date, keep the final "
        "script below 110 words, and avoid reading URLs aloud.",
        "Parallel current research must be compressed for a voice interface.",
        ("researcher", "summariser", "answer_with_evidence"),
    ),
    ChannelScenario(
        "package_advisory", "imap",
        "This email says Node.js 24 has an actively exploited vulnerability and that we must downgrade today. "
        "Check the official Node.js security releases and the CVE record, identify affected versions, and draft "
        "a technically precise reply to the engineering team.",
        "Turns an untrusted email claim into a primary-source incident response.",
        ("researcher", "fetch_url", "coder_validator", "answer_with_evidence"),
    ),
    ChannelScenario(
        "deployment_event", "webhook",
        "Deployment event: service=checkout, environment=production, previous_error_rate=0.7%, "
        "current_error_rate=6.4%, deployment=https://example.invalid/deploy/841. Determine whether the change "
        "is material, calculate the relative increase, and produce a rollback recommendation with assumptions.",
        "Treats an external event as evidence, performs deterministic arithmetic, and decides whether to act.",
        ("calculate", "coder_validator", "answer_with_evidence"),
    ),
    ChannelScenario(
        "semantic_handbook", "webui",
        "Index sandbox file handbook.md with semantic chunking. Then answer: what is the escalation policy when "
        "a production change causes customer-visible errors? Cite the indexed source and show how many chunks "
        "were created.",
        "Executes the real semantic indexing pipeline, retrieves from it, and reports provenance.",
        ("index_file", "memory_recall", "answer_with_evidence"),
    ),
    ChannelScenario(
        "spoken_purchase", "local_mic",
        "I need a laptop for local Ollama models under INR 120,000. Compare the Lenovo LOQ 15IRX9, ASUS TUF "
        "Gaming A15 FA507, and Acer Nitro V 15 ANV15-51 using their current Indian manufacturer pages. Check "
        "price, RAM expandability, and dedicated GPU memory, then give me a short spoken recommendation that "
        "explicitly says when specifications are unavailable or not comparable.",
        "Current purchase research is parallelized and reconciled without inventing comparable specifications.",
        ("researcher", "coder_validator", "answer_with_evidence"),
    ),
    ChannelScenario(
        "human_approval", "gmail",
        "Draft a calm reply to the incident thread saying the root cause is still under investigation. Do not "
        "finalize the reply yet: first ask me whether to say 'next update in 30 minutes' or 'next update by 6 PM'.",
        "The graph must stop at a human decision and continue from the later channel reply.",
        ("request_approval", "answer_with_evidence"),
        follow_up="Use 'next update in 30 minutes'. Approved.",
    ),
    ChannelScenario(
        "verified_artifact", "telegram",
        "Write a Markdown runbook named deploy-checklist.md with pre-deploy, deploy, rollback, and verification "
        "sections. Then compute its SHA-256 and verify the created artifact before telling me it is ready.",
        "Plans a sequence of file mutations and independent integrity checks.",
        ("write_file", "file_sha256", "answer_with_evidence"),
    ),
    ChannelScenario(
        "parallel_incident", "slack",
        "Investigate why users in Singapore might see elevated latency right now. Check our supplied event facts, "
        "the current status pages of Cloudflare, AWS Singapore, and Google Cloud Singapore in parallel, then post "
        "one evidence-ranked hypothesis and the next measurement to collect.",
        "Launches independent researchers concurrently and waits for their outcomes before synthesis.",
        ("researcher", "distiller", "answer_with_evidence"),
    ),
    ChannelScenario(
        "cross_channel_memory", "teams",
        "Use the durable preferences I previously gave you on WhatsApp. Suggest two Bengaluru dinner areas that "
        "respect them, verify current metro access from official sources, and state which remembered constraints "
        "you applied.",
        "Tests installation-owner identity continuity, scoped recall, and fresh external research across channels.",
        ("memory_recall", "researcher", "answer_with_evidence"),
    ),
    ChannelScenario(
        "three_way_research", "discord",
        "For a laptop-hosted autonomous agent, independently investigate the current official guidance for Gmail "
        "push notifications, GitHub webhook redelivery, and Kubernetes watch recovery. Wait for all three research "
        "outcomes, then design one restart-safe event ingestion contract without service-specific branches.",
        "Forces parallel specialists followed by a domain-neutral architectural synthesis.",
        ("researcher", "distiller", "coder_validator", "answer_with_evidence"),
    ),
)


# Observable proof criteria. Each inner tuple is an acceptable capability
# family; at least one member must appear. These judge explicit user-visible
# requirements, not an exact graph or agent count.
REQUIRED_TOOL_GROUPS = {
    "travel_weather": (("current_datetime",), ("researcher", "web_search"), ("answer_with_evidence",)),
    "remember_preference": (("remember_explicit_fact",), ("answer_with_evidence",)),
    "security_mail": (("researcher", "web_search"), ("answer_with_evidence",)),
    "platform_comparison": (("researcher", "web_search"), ("answer_with_evidence",)),
    "csv_grading": (("query_csv",), ("answer_with_evidence",)),
    "python_free_threading": (("researcher", "web_search"), ("answer_with_evidence",)),
    "a2a_transport": (("researcher", "web_search", "fetch_url"), ("answer_with_evidence",)),
    "viral_claim": (("researcher", "web_search"), ("answer_with_evidence",)),
    "calendar_artifacts": (("create_calendar_events",), ("verify_artifact",), ("answer_with_evidence",)),
    "airport_brief": (("current_datetime",), ("researcher", "web_search"), ("answer_with_evidence",)),
    "voice_briefing": (("researcher", "web_search"), ("answer_with_evidence",)),
    "package_advisory": (("researcher", "web_search"), ("answer_with_evidence",)),
    "deployment_event": (("calculate",), ("answer_with_evidence",)),
    "semantic_handbook": (("index_file",), ("answer_with_evidence",)),
    "spoken_purchase": (("researcher", "web_search"), ("answer_with_evidence",)),
    "human_approval": (("request_approval",), ("answer_with_evidence",)),
    "verified_artifact": (("write_file",), ("verify_artifact",), ("answer_with_evidence",)),
    "parallel_incident": (("researcher", "web_search"), ("answer_with_evidence",)),
    "cross_channel_memory": (("memory_recall", "retriever"), ("researcher", "web_search"),
                             ("answer_with_evidence",)),
    "three_way_research": (("researcher", "web_search"), ("answer_with_evidence",)),
}

REQUIRE_PARALLEL = {"parallel_incident", "three_way_research"}
REQUIRE_WAIT_RESUME = {"human_approval"}
