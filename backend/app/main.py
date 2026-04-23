"""
docbase — FastAPI application entry point.
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from starlette.middleware.base import BaseHTTPMiddleware

from app.api.v1 import router as api_v1_router
from app.core.config import get_settings
from app.core.exceptions import PlatformError
from app.core.limiter import limiter
from app.core.logging import get_logger, setup_logging
from app.core.redis import close_redis

settings = get_settings()
logger = get_logger(__name__)

# ─── Request body size limits ─────────────────────────────────────────────────
# Default: keep JSON/chat payloads bounded. PDF upload allows 20 MB (see sources API)
# plus headroom for multipart boundaries.
_MAX_JSON_BODY_BYTES = 1 * 1024 * 1024  # 1 MB
_MAX_MULTIPART_UPLOAD_BYTES = 22 * 1024 * 1024  # ≥ app.api.v1.sources._MAX_PDF_BYTES + overhead


class ContentSizeLimitMiddleware(BaseHTTPMiddleware):
    """Reject requests whose Content-Length exceeds the configured limit."""

    async def dispatch(self, request: Request, call_next):  # type: ignore[override]
        content_length = request.headers.get("content-length")
        if not content_length:
            return await call_next(request)
        limit = (
            _MAX_MULTIPART_UPLOAD_BYTES
            if request.url.path.rstrip("/").endswith("/upload-pdf")
            else _MAX_JSON_BODY_BYTES
        )
        if int(content_length) > limit:
            return JSONResponse(
                status_code=413,
                content={"error": "request_too_large", "message": "Request body exceeds limit"},
            )
        return await call_next(request)


# ─── Security headers ─────────────────────────────────────────────────────────

class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Add defensive HTTP security headers to every response."""

    async def dispatch(self, request: Request, call_next):  # type: ignore[override]
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        response.headers["Permissions-Policy"] = "geolocation=(), camera=(), microphone=()"
        # Tight CSP: API responses are JSON — no scripts, frames, or external resources needed.
        # Public share pages served by the frontend (Vite/React) should set their own CSP.
        response.headers["Content-Security-Policy"] = (
            "default-src 'none'; frame-ancestors 'none'"
        )
        if settings.is_production:
            response.headers["Strict-Transport-Security"] = (
                "max-age=63072000; includeSubDomains; preload"
            )
        return response


# ─── Lifespan ─────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    logger.info("startup", env=settings.app_env)
    yield
    await close_redis()
    logger.info("shutdown")


# ─── App ──────────────────────────────────────────────────────────────────────

app = FastAPI(
    title="docbase",
    version="0.1.0",
    docs_url="/api/docs" if not settings.is_production else None,
    redoc_url="/api/redoc" if not settings.is_production else None,
    openapi_url="/api/openapi.json" if not settings.is_production else None,
    lifespan=lifespan,
)

# Attach limiter to app state so SlowAPI can find it
app.state.limiter = limiter

# ─── Middleware (applied in reverse registration order) ───────────────────────
# Order after reversal: CORS → ContentSizeLimit → SecurityHeaders → SlowAPI

app.add_middleware(SlowAPIMiddleware)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(ContentSizeLimitMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_allow_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Accept"],
)

# ─── Exception handlers ───────────────────────────────────────────────────────

app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


@app.exception_handler(PlatformError)
async def platform_error_handler(request: Request, exc: PlatformError) -> JSONResponse:
    logger.warning(
        "platform_error",
        error_code=exc.error_code,
        message=exc.message,
        path=request.url.path,
    )
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": exc.error_code,
            "message": exc.message,
            "detail": exc.detail,
        },
    )

# ─── Routes ───────────────────────────────────────────────────────────────────

app.include_router(api_v1_router, prefix="/api/v1")


@app.get("/health")
async def health() -> dict:
    # Do not expose environment name — leaks deployment context to anonymous callers
    return {"status": "ok"}
