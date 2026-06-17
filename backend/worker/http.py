"""Worker HTTP service — POST /wake triggers queue drain."""

from __future__ import annotations

import secrets
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

from fastapi import FastAPI, Header, HTTPException

from infrastructure.config.settings import get_settings

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

from worker.runtime import WorkerRuntime

runtime = WorkerRuntime()


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    await runtime.start()
    yield
    await runtime.stop()


app = FastAPI(title="PR Reviewer Worker", lifespan=lifespan)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/wake")
async def wake(x_worker_secret: str = Header(..., alias="X-Worker-Secret")) -> dict[str, str]:
    settings = get_settings()
    expected = settings.worker_wake_secret
    if not expected or not secrets.compare_digest(x_worker_secret, expected):
        raise HTTPException(status_code=401, detail="Invalid worker secret")

    runtime.signal_wake()
    return {"status": "accepted"}
