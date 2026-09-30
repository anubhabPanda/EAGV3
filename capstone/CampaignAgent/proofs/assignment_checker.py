"""A simulated LMS test runner for a student-friendly durable-wait proof.

The fixed report belongs to the external test fixture. S17 receives it only
through the same generic launch-job callback contract used by any program.
"""

from __future__ import annotations

import asyncio
import uuid

import httpx
from fastapi import BackgroundTasks, FastAPI

from proofs.async_worker import Job

app = FastAPI(title="simulated assignment test runner")


async def finish(job: Job, handle: str) -> None:
    await asyncio.sleep(1)
    headers = {"Authorization": f"Bearer {job.callback_token}"} if job.callback_token else {}
    report = {
        "assignment": "Event-driven agent submission",
        "tests_total": 10,
        "tests_passed": 8,
        "failed_tests": [
            {"name": "duplicate_webhook_is_ignored",
             "message": "The same delivery created a second run."},
            {"name": "resume_after_restart",
             "message": "The waiting job handle was not restored after restart."},
        ],
    }
    async with httpx.AsyncClient(timeout=120) as client:
        await client.post(job.callback_url, headers=headers, json={
            "handle": handle,
            "event_type": job.callback_event_type,
            "success": True,
            "payload": report,
        })


@app.post("/jobs", status_code=202)
async def jobs(job: Job, background: BackgroundTasks):
    handle = f"assignment-{uuid.uuid4().hex[:12]}"
    background.add_task(finish, job, handle)
    return {"handle": handle}
