"""A generic callback worker used only by the live durable-wait proof."""

from __future__ import annotations

import asyncio
import hashlib
import uuid
from typing import Any

import httpx
from fastapi import BackgroundTasks, FastAPI
from pydantic import BaseModel, Field

app = FastAPI(title="generic asynchronous proof worker")


class Job(BaseModel):
    task: str = Field(min_length=1)
    run_id: str
    node_id: str
    callback_url: str
    callback_event_type: str
    callback_token: str | None = None


async def finish(job: Job, handle: str) -> None:
    await asyncio.sleep(1)
    headers = {"Authorization": f"Bearer {job.callback_token}"} if job.callback_token else {}
    payload: dict[str, Any] = {
        "handle": handle,
        "event_type": job.callback_event_type,
        "success": True,
        "payload": {"worker": "generic-proof-worker", "completed_task": job.task,
                    "character_count": len(job.task),
                    "sha256": hashlib.sha256(job.task.encode()).hexdigest()},
    }
    async with httpx.AsyncClient(timeout=120) as client:
        await client.post(job.callback_url, json=payload, headers=headers)


@app.post("/jobs", status_code=202)
async def jobs(job: Job, background: BackgroundTasks):
    handle = f"job-{uuid.uuid4().hex[:12]}"
    background.add_task(finish, job, handle)
    return {"handle": handle}
