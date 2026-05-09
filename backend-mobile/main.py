from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI, Response

import models  # noqa: F401 — register ORM models
from database import check_db_connection
from routers import analyses, stocks


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    check_db_connection()
    yield


app = FastAPI(title="GREED Mobile API", lifespan=lifespan)


@app.middleware("http")
async def disable_response_cache(request, call_next) -> Response:
    response = await call_next(request)
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"
    return response

app.include_router(analyses.router)
app.include_router(stocks.router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
