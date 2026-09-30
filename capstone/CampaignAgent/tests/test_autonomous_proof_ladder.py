import base64
import json
from datetime import UTC, datetime
from pathlib import Path

from sourcecode.events.adapters import cron_event, gmail_pubsub_event, webhook_event

ROOT = Path(__file__).resolve().parents[1]


def test_twenty_replaceable_tasks_are_data_not_runtime_branches():
    task_file = ROOT / "proofs" / "tasks" / "autonomous_20.jsonl"
    tasks = [json.loads(line) for line in task_file.read_text().splitlines() if line.strip()]
    assert len(tasks) == 20
    assert [task["id"] for task in tasks] == [f"A{index:02d}" for index in range(1, 21)]
    assert {task["level"] for task in tasks} == {"simple", "moderate", "advanced", "complex"}

    production = "\n".join(path.read_text(encoding="utf-8")
                           for path in (ROOT / "sourcecode").rglob("*.py"))
    # Distinctive canaries make this stronger than searching only task ids:
    # neither prompts nor a disguised phrase router may leak into production.
    for task in tasks:
        assert task["canary"] not in production
        assert task["problem"] not in production


def test_cron_webhook_and_gmail_all_end_as_the_same_event_contract():
    instant = datetime(2026, 8, 5, 9, 30, tzinfo=UTC)
    cron = cron_event("morning-digest", occurred_at=instant, data={"window": "24h"})
    webhook = webhook_event(source="github.webhook", delivery_id="delivery-4",
                            event_type="checks.failed", payload={"sha": "abc"}, occurred_at=instant)
    gmail_data = base64.b64encode(json.dumps(
        {"emailAddress": "agent@example.com", "historyId": "991"}
    ).encode()).decode()
    gmail = gmail_pubsub_event({"message": {"messageId": "gmail-4", "publishTime": instant.isoformat(),
                                             "data": gmail_data}})

    assert cron.type == "schedule.tick" and cron.source == "cron.morning-digest"
    assert webhook.id == "delivery-4" and webhook.data == {"sha": "abc"}
    assert gmail.type == "gmail.history.changed" and gmail.data["historyId"] == "991"
    assert type(cron) is type(webhook) is type(gmail)
