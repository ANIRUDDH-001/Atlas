import uuid
import time
import json
import asyncio
from contextlib import asynccontextmanager
from datetime import datetime

import structlog
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse

MAX_REQUEST_BODY_BYTES = 5 * 1024 * 1024  # 5MB
from sqlalchemy.exc import OperationalError

from app.config import get_settings
from app.db import engine
from app.cache import close_redis as close_cache
from app.exceptions import DatabaseUnavailableError, StoreIntelligenceError

# ── Configure structlog ───────────────────────────────────────────────────────
structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.stdlib.add_log_level,
        structlog.processors.JSONRenderer(),
    ]
)
logger = structlog.get_logger()
settings = get_settings()


# ── Lifespan (startup / shutdown) ─────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("startup", service="store-intelligence-api",
                database=settings.database_url.split("@")[-1])

    # Load POS transactions on startup
    from app.pos_loader import load_pos_transactions
    from app.db import AsyncSessionLocal
    async with AsyncSessionLocal() as session:
        try:
            count = await load_pos_transactions(session)
            logger.info("pos_transactions_loaded", count=count)
        except Exception as exc:
            # POS load failure is non-fatal — metrics will show null conversion
            logger.error("pos_load_failed", error=type(exc).__name__)

    # Cache warm-up
    from app.cache import get_redis
    try:
        redis = await get_redis()
        await redis.ping()
        logger.info("redis_warmed_up")
    except Exception as exc:
        logger.warning("redis_warm_up_failed", error=type(exc).__name__)

    yield
    await close_cache()
    logger.info("shutdown", service="store-intelligence-api")


# ── App factory ────────────────────────────────────────────────────────────────
app = FastAPI(
    title="Store Intelligence API",
    version="0.1.0",
    description="Purplle Tech Challenge 2026 — AI-powered retail analytics",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)


# ── CORS ───────────────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://dashboard:80"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


# ── Request logging middleware ─────────────────────────────────────────────────
@app.middleware("http")
async def limit_request_size(request: Request, call_next):
    content_length = request.headers.get("content-length")
    if content_length and int(content_length) > MAX_REQUEST_BODY_BYTES:
        return JSONResponse(
            status_code=413,
            content={"error": "request_too_large",
                     "max_bytes": MAX_REQUEST_BODY_BYTES},
        )
    return await call_next(request)

@app.middleware("http")
async def log_requests(request: Request, call_next):
    trace_id = str(uuid.uuid4())
    request.state.trace_id = trace_id
    start = time.perf_counter()

    response = await call_next(request)

    latency_ms = round((time.perf_counter() - start) * 1000, 2)
    logger.info(
        "request",
        trace_id=trace_id,
        store_id=request.path_params.get("store_id"),
        endpoint=request.url.path,
        method=request.method,
        latency_ms=latency_ms,
        status_code=response.status_code,
    )
    response.headers["X-Trace-Id"] = trace_id
    return response


# ── Global exception handlers ──────────────────────────────────────────────────
@app.exception_handler(OperationalError)
async def db_op_error_handler(request: Request, exc: OperationalError):
    import traceback
    logger.error("db_unavailable", path=request.url.path, error=type(exc).__name__, trace_id=getattr(request.state, "trace_id", None))
    return JSONResponse(
        status_code=503,
        content={
            "error": "service_unavailable",
            "detail": "Database is temporarily unavailable.",
            "trace_id": getattr(request.state, "trace_id", None),
        },
    )


@app.exception_handler(DatabaseUnavailableError)
async def db_custom_error(request: Request, exc: DatabaseUnavailableError):
    return JSONResponse(
        status_code=503,
        content={
            "error": "service_unavailable",
            "detail": str(exc),
            "trace_id": getattr(request.state, "trace_id", None),
        },
    )


@app.exception_handler(Exception)
async def generic_error(request: Request, exc: Exception):
    logger.error("unhandled_exception", path=request.url.path,
                 error=type(exc).__name__, detail=str(exc),
                 trace_id=getattr(request.state, "trace_id", None))
    return JSONResponse(
        status_code=500,
        content={
            "error": "internal_server_error",
            "detail": "An unexpected error occurred.",
            "trace_id": getattr(request.state, "trace_id", None),
        },
    )


# ── Router includes ────────────────────────────────────────────────────────────
# Each router is imported from its module. Modules return 501 until implemented.
from app.health import router as health_router
from app.ingestion import router as ingest_router
from app.metrics import router as metrics_router
from app.funnel import router as funnel_router
from app.heatmap import router as heatmap_router
from app.anomalies import router as anomalies_router

app.include_router(health_router)
app.include_router(ingest_router)
app.include_router(metrics_router, prefix="/stores")
app.include_router(funnel_router, prefix="/stores")
app.include_router(heatmap_router, prefix="/stores")
app.include_router(anomalies_router, prefix="/stores")


# ── SSE stream endpoint ────────────────────────────────────────────────────────
@app.get(
    "/stores/{store_id}/metrics/stream",
    summary="Server-Sent Events stream of live metrics",
    tags=["streaming"],
)
async def metrics_stream(store_id: str, request: Request):
    """
    Streams MetricsResponse JSON as SSE events every 5 seconds.
    Dashboard connects once and receives live updates.
    """
    async def event_generator():
        from app.metrics import compute_metrics
        while True:
            if await request.is_disconnected():
                break
            try:
                metrics = await compute_metrics(store_id)
                data = metrics.model_dump_json()
                yield f"data: {data}\n\n"
            except Exception as e:
                logger.warning("sse_metrics_error", store_id=store_id,
                               error=str(e))
                yield f"data: {json.dumps({'error': 'internal_server_error'})}\n\n"
            await asyncio.sleep(5)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
