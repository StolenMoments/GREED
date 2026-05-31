from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from logging import LogRecord
from typing import AsyncGenerator

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import DBAPIError, OperationalError

from backend.database import (
    DATABASE_UNAVAILABLE_MESSAGE,
    SessionLocal,
    get_database_health,
    init_db,
    is_database_unavailable_error,
    mark_database_unavailable,
)
from backend.routers import (
    analyses_router,
    backtest_router,
    candidates_router,
    jobs_router,
    runs_router,
    stats_router,
    stock_router,
    stocks_router,
    tickers_router,
)


class UvicornAccessLogFilter(logging.Filter):
    def filter(self, record: LogRecord) -> bool:
        status_code = self._get_status_code(record)
        return status_code is None or not 200 <= status_code < 300

    @staticmethod
    def _get_status_code(record: LogRecord) -> int | None:
        if not isinstance(record.args, tuple) or not record.args:
            return None

        try:
            return int(record.args[-1])
        except (TypeError, ValueError):
            return None


def configure_access_log_filter() -> None:
    access_logger = logging.getLogger("uvicorn.access")
    if any(isinstance(log_filter, UvicornAccessLogFilter) for log_filter in access_logger.filters):
        return

    access_logger.addFilter(UvicornAccessLogFilter())


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    try:
        init_db()
        _seed_default_backtest_universe()
        _mark_orphaned_backtest_jobs_failed()
    except (DBAPIError, OperationalError) as exc:
        mark_database_unavailable(exc)
    yield


def _seed_default_backtest_universe() -> None:
    from scripts.backtest.universe import ensure_default_universe_seeded

    with SessionLocal() as db:
        ensure_default_universe_seeded(db)


def _mark_orphaned_backtest_jobs_failed() -> None:
    from backend.timezone import seoul_now
    from sqlalchemy import text

    with SessionLocal() as db:
        db.execute(
            text(
                "UPDATE analysis_backtest_jobs"
                " SET status='failed',"
                " error_message='서버 재시작으로 인해 중단됨',"
                " completed_at=:now"
                " WHERE status='running'"
            ),
            {"now": seoul_now()},
        )
        db.execute(
            text(
                "UPDATE backtest_strategy_jobs"
                " SET status='failed',"
                " error_message='server restarted while job was running',"
                " completed_at=:now"
                " WHERE status='running'"
            ),
            {"now": seoul_now()},
        )
        db.commit()


_cors_origin = os.getenv("CORS_ORIGIN", "http://localhost:5173")
configure_access_log_filter()

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
app.include_router(stats_router)
app.include_router(backtest_router)
app.include_router(candidates_router)
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
