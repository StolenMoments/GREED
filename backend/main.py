from __future__ import annotations

import os
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import DBAPIError, OperationalError

from backend.database import (
    DATABASE_UNAVAILABLE_MESSAGE,
    get_database_health,
    init_db,
    is_database_unavailable_error,
    mark_database_unavailable,
)
from backend.routers import analyses_router, jobs_router, runs_router, stock_router, stocks_router, tickers_router


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    try:
        init_db()
    except (DBAPIError, OperationalError) as exc:
        mark_database_unavailable(exc)
    yield


_cors_origin = os.getenv("CORS_ORIGIN", "http://localhost:5173")

app = FastAPI(title="Greed API", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[_cors_origin],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(runs_router)
app.include_router(analyses_router)
app.include_router(stock_router)
app.include_router(stocks_router)
app.include_router(jobs_router)
app.include_router(tickers_router)


@app.exception_handler(OperationalError)
@app.exception_handler(DBAPIError)
async def database_exception_handler(request: Request, exc: DBAPIError) -> JSONResponse:
    if not is_database_unavailable_error(exc):
        raise

    mark_database_unavailable(exc)
    return JSONResponse(
        status_code=503,
        content={
            "detail": DATABASE_UNAVAILABLE_MESSAGE,
            "code": "database_unavailable",
        },
    )


@app.get("/api/health")
def health_endpoint() -> dict[str, object]:
    return {"api": "ok", "database": get_database_health()}
