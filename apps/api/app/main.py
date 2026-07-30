from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.errors import register_error_handlers
from app.api.v1.routes.analyses import router as analyses_router
from app.api.v1.routes.comparables import router as comparables_router
from app.api.v1.routes.health import router as health_router
from app.api.v1.routes.me import router as me_router
from app.api.v1.routes.opportunities import router as opportunities_router
from app.api.v1.routes.platforms import router as platforms_router
from app.api.v1.routes.portfolio import router as portfolio_router
from app.shared.config import get_settings
from app.shared.logging import configure_logging
from app.shared.middleware import RequestContextMiddleware


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level)

    app = FastAPI(title="KAIROS API", version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_allowed_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "PATCH"],
        allow_headers=["*"],
    )
    app.add_middleware(RequestContextMiddleware)
    register_error_handlers(app)

    app.include_router(health_router, prefix="/api/v1")
    app.include_router(me_router, prefix="/api/v1")
    app.include_router(opportunities_router, prefix="/api/v1")
    app.include_router(platforms_router, prefix="/api/v1")
    app.include_router(comparables_router, prefix="/api/v1")
    app.include_router(analyses_router, prefix="/api/v1")
    app.include_router(portfolio_router, prefix="/api/v1")

    return app


app = create_app()
