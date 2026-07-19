"""
Main FastAPI application entry point (NightForge control-plane).
"""
import logging


def _configure_logging() -> None:
    """Configure app log levels."""
    root = logging.getLogger()
    if not root.handlers:
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        )
    for name in ("sqlalchemy.engine", "sqlalchemy.pool", "sqlalchemy.dialects"):
        logging.getLogger(name).setLevel(logging.ERROR)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)


_configure_logging()

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from api.v1.router import router as api_router
from core.config import settings

app = FastAPI(
    title="NightForge API",
    description="Control-plane for autonomous overnight Claude Code runs",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """
    Return a clean 500 that still carries CORS headers.

    Args:
        request: The failing request.
        exc: The unhandled exception.

    Returns:
        A JSON 500 response with CORS headers when the origin is allowed.
    """
    logging.getLogger(__name__).exception(
        "Unhandled error on %s %s", request.method, request.url.path
    )
    headers: dict = {}
    origin = request.headers.get("origin")
    if origin and origin in settings.allowed_cors_origins:
        headers["Access-Control-Allow-Origin"] = origin
        headers["Access-Control-Allow-Credentials"] = "true"
        headers["Vary"] = "Origin"
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "Internal server error"},
        headers=headers,
    )


app.include_router(api_router, prefix=settings.api_prefix)


@app.on_event("startup")
def _ensure_schema() -> None:
    """Create missing tables/columns (e.g. ``projects.allow_push``) on boot."""
    from core.database import init_db

    init_db()


@app.get("/", tags=["root"])
async def root() -> dict:
    """
    Root endpoint.

    Returns:
        Welcome message and API information.
    """
    return {
        "message": "Welcome to NightForge API",
        "version": "0.1.0",
        "docs": "/docs",
        "health": f"{settings.api_prefix}/health",
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host=settings.host, port=settings.port, reload=settings.debug)
