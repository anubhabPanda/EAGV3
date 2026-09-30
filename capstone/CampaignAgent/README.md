# Comms Agent — a general live-graph agent for campaign operations

Comms Agent is a capability-driven agent loop built on a durable graph, memory,
A2A, UI, budget controller and telemetry. A gateway service connects that loop
to every enabled channel through one shared envelope.

The planner does **not** build the whole DAG up front. It proposes only the next
runnable frontier, the runtime launches independent nodes together, and every
outcome causes another planning round. The graph therefore grows from evidence:

```text
goal → plan next frontier → run independent work concurrently
     → observe real outcomes → critique evidence → expand or answer
```

There is no prompt classifier, benchmark router, or deterministic task
fallback. A model may propose work, but Python owns the boundary: only
registered capabilities with valid arguments and valid existing dependencies
can enter the graph.

## What makes it general

- `sourcecode/capabilities.py` is the complete manifest the planner sees. It
  describes what the agent can do and strictly validates every argument.
- `sourcecode/planner.py` asks for only the next useful frontier. A new task may
  depend only on evidence that already exists—not on an imagined future task.
- Independent tasks in one frontier run concurrently. Synthesis is held until
  active siblings finish, so the agent does not answer while useful evidence is
  still arriving.
- Before a terminal answer, a separate evidence-readiness pass checks the
  original request against accumulated outcomes. Missing facts cause more work,
  not cosmetic rewriting.
- Equivalent active work is deduplicated even when the planner invents a new
  node ID. Run and frontier limits keep an unproductive loop finite.
- Invalid planner output is repaired through the model and recorded. If repair
  fails, the run fails visibly; it never switches to a hidden, hardcoded agent.

## Campaign capabilities

Comms Agent talks to a remote, token-authenticated MCP server that exposes
CRUD and state-transition tools for email campaigns, audiences and
subscribers. Every capability below maps to exactly one MCP tool, declared
once in `sourcecode/capabilities.py` and invoked by
`sourcecode/workers/campaign.py`.

**Email campaigns**
- `list_email_campaigns` — list campaigns, filterable by status or search text
- `get_email_campaign` — fetch one campaign by ID
- `create_email_campaign` — create a new draft campaign
- `update_email_campaign` — update an existing campaign
- `delete_email_campaign` — delete a campaign
- `schedule_email_campaign` — transition draft → scheduled
- `cancel_scheduled_email_campaign` — transition scheduled → cancelled
- `pause_email_campaign` — transition sending → paused
- `cancel_paused_email_campaign` — transition paused → cancelled
- `save_email_campaign_draft` — save a campaign back to draft

**Audiences**
- `list_campaign_audiences` / `get_campaign_audience` — saved audience segments
- `preview_campaign_audience` — preview which CRM contacts a segment
  definition matches, without saving it
- `list_crm_campaign_audiences` — list CRM audiences via the CRM endpoint

**Links & recipients**
- `list_campaign_links` / `get_campaign_link` — tracked links for a campaign
- `list_campaign_recipients` / `get_campaign_recipient` — delivery, open,
  click and unsubscribe status per recipient

**Subscribers & lists**
- `list_subscribers` / `get_subscriber` — subscribers, filterable by status
  (active, unsubscribed, bounced, complained, pending) or list
- `create_subscriber` / `update_subscriber` / `delete_subscriber`
- `list_subscriber_lists` / `get_subscriber_list` — mailing lists
- `create_subscriber_list` / `update_subscriber_list`
- `list_public_subscriber_lists` — lists exposed on the public signup endpoint

## Other capabilities

The registry also includes scoped memory recall and explicit remembering,
semantic document indexing, web search and URL reading, bounded research,
retrieval/distillation/validation, sandboxed file access, calendar artifact
creation, A2A delegation, UI composition and evidence-grounded answers.

Web research uses a multi-backend search client and then reads the returned
pages. Search snippets and pages are untrusted evidence. Crucially, if search
finds no usable URL—or no page can be read—the researcher returns
`insufficient: true` and does **not** ask a model to synthesize facts.

## Unattended operation

Everything above assumes somebody asked. The autonomy layer is what handles
the case where nobody did, and where nobody is watching either.

- `sourcecode/events/` normalises cron ticks, webhooks, Gmail Pub/Sub, channel
  messages and job callbacks into one `EventEnvelope`, deduplicates on
  `(source, id)`, and records a relevance decision for every matching
  subscription — including the decisions that were "no".
- **Events are facts; subscriptions are intent and authority.** An event can
  never write the instruction, the allowed side effects or the budget that
  govern it. That is why writing a subscription is a control-plane action.
- `sourcecode/auth.py` gates every write path and **fails closed**. With no
  control token configured, `PUT /v1/agent/subscriptions/{id}`,
  `POST /v1/agent/events`, `POST /v1/agent/runs` and the resume route all answer
  `503` rather than serving anonymously.
- `sourcecode/events/governor.py` bounds operation over a **window**, not a
  request: `daily_budget`, `max_runs_per_day` and `daily_triage_budget` bound
  an agent that starts its own runs. It also rate-limits per source and
  refuses events this agent itself caused, so a reply into a watched mailbox
  cannot become a loop.
- `sourcecode/events/lease.py` stops a periodic trigger overlapping itself.
- `sourcecode/events/report.py` publishes a heartbeat (`GET /v1/agent/liveness`)
  and a human-readable account of a period nobody watched
  (`GET /v1/agent/report`).

## Key modules

- `sourcecode/core/live_graph/`: event-sourced executor, patches and replay
- `sourcecode/core/memory/`: typed, scoped memory and semantic chunking
- `sourcecode/core/a2a/`: Agent Cards, JSON-RPC and optional gRPC
- `sourcecode/ui/`: catalog validation, A2UI surfaces, AG-UI and HITL
- `sourcecode/economics/`: model tiers, hard budget admission and ledger
- `sourcecode/telemetry/`: journal-to-OpenTelemetry span export
- `sourcecode/workers/campaign.py`: dispatches campaign capabilities to the MCP server

## Run locally

```bash
uv sync
cp .env.example .env
uv run pytest -q
uv run ruff check .
uv run sourcecode serve
```

Comms Agent defaults to `http://127.0.0.1:8113`. Useful environment variables
are documented in `.env.example`, including the gateway provider, sandbox
root, and the control/channel/completion tokens gating every write path. The
control plane has no unauthenticated mode: with no token configured, write
routes refuse to serve rather than serving anonymously.

Example run:

```bash
curl -s http://127.0.0.1:8113/v1/agent/runs \
  -H 'content-type: application/json' \
  -H 'Authorization: Bearer <control-token>' \
  -d '{
    "tenant_id":"demo",
    "project_id":"campaigns",
    "user_id":"user",
    "prompt":"List all email campaigns"
  }' | jq '{status, answer, graph: .graph.nodes, planner: .trace.planner}'
```

## Honest limits

A general agent is bounded by its registered capabilities, source availability
and models. The evidence critic is an additional model judgment, not a
theorem. The hard guarantees are narrower and enforced in code: authority
validation, existing-evidence dependencies, bounded graph/frontier size,
deduplication, metered provider calls, budget admission, durable outcomes, and
no research synthesis without readable sources.
