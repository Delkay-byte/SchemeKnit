"""
SchemeKnit Backend - Production Application
"""

import os
import sys
from contextlib import asynccontextmanager
from datetime import datetime, date
from pathlib import Path

from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError

from .config import get_settings
from .database import init_db, SessionLocal
from .logging_config import setup_logging, get_logger, log_error

settings = get_settings()
setup_logging(settings.LOG_LEVEL)
logger = get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings.validate_production()
    init_db()
    try:
        from .migration_runner import run_all_migrations
        results = run_all_migrations()
        if results:
            for v, n, s in results:
                logger.info("migration_applied", version=v, name=n, status=s)
    except Exception as e:
        logger.error("migration_failed", error=str(e))
        raise
    _seed_global_holidays()
    _seed_payment_config()
    _seed_product_plans()
    logger.info("SchemeKnit started", version=settings.APP_VERSION, debug=settings.DEBUG)
    yield
    logger.info("SchemeKnit shutting down")


def _seed_global_holidays():
    from .database import HolidayDB
    db = SessionLocal()
    try:
        if db.query(HolidayDB).filter(HolidayDB.owner_id.is_(None)).count() == 0:
            gh_holidays = [
                ("New Year's Day", 1, 1),
                ("Independence Day", 3, 6),
                ("Good Friday", 4, 18),
                ("Easter Saturday", 4, 19),
                ("Easter Monday", 4, 21),
                ("Labour Day", 5, 1),
                ("Africa Day", 5, 25),
                ("Republic Day", 7, 1),
                ("Constitution Day", 9, 21),
                ("Farmers' Day", 12, 5),
                ("Christmas Day", 12, 25),
                ("Boxing Day", 12, 26),
            ]
            from .database import generate_id
            for name, month, day in gh_holidays:
                db.add(HolidayDB(
                    id=generate_id(),
                    name=name,
                    date=date(2026, month, day),
                    is_recurring=True,
                ))
            db.commit()
    except Exception:
        db.rollback()
    finally:
        db.close()


def _seed_payment_config():
    from .database import PaymentConfigDB
    db = SessionLocal()
    try:
        if db.query(PaymentConfigDB).filter(
            PaymentConfigDB.config_key == "payment_instructions"
        ).count() == 0:
            from .database import generate_id
            config = {
                "mtn_momo": {
                    "phone": "0553976334",
                    "account_name": "Kobla Saviour Amegayie",
                    "enabled": True,
                },
                "bank_transfer": {
                    "bank": "GCB Bank",
                    "account_number": "5151010019541",
                    "branch": "Abor",
                    "account_name": "Kobla Saviour Amegayie",
                    "enabled": True,
                },
                "currency": "GHS",
            }
            db.add(PaymentConfigDB(
                id=generate_id(),
                config_key="payment_instructions",
                config_value=config,
            ))
            db.commit()
    except Exception:
        db.rollback()
    finally:
        db.close()


def _seed_product_plans():
    from .database import ProductPlanDB
    db = SessionLocal()
    try:
        if db.query(ProductPlanDB).count() == 0:
            from .database import generate_id
            plans = [
                {
                    "name": "Teacher Monthly",
                    "description": "Monthly subscription for individual teachers",
                    "product_type": "subscription",
                    "price": 50.0,
                    "duration_days": 30,
                    "features": ["ai_basic", "cloud_sync", "template_import", "content_library"],
                    "active": True,
                },
                {
                    "name": "Teacher Annual",
                    "description": "Annual subscription for individual teachers (20% discount)",
                    "product_type": "subscription",
                    "price": 480.0,
                    "duration_days": 365,
                    "features": ["ai_basic", "cloud_sync", "template_import", "content_library"],
                    "active": True,
                },
                {
                    "name": "School Monthly",
                    "description": "Monthly subscription for schools (multi-teacher)",
                    "product_type": "subscription",
                    "price": 500.0,
                    "duration_days": 30,
                    "features": ["ai_enhanced", "cloud_sync", "template_import", "content_library", "multi_teacher", "priority_support"],
                    "active": True,
                },
            ]
            for plan in plans:
                db.add(ProductPlanDB(
                    id=generate_id(),
                    name=plan["name"],
                    description=plan["description"],
                    product_type=plan["product_type"],
                    price=plan["price"],
                    duration_days=plan.get("duration_days"),
                    features=plan["features"],
                    active=plan["active"],
                ))
            db.commit()
    except Exception:
        db.rollback()
    finally:
        db.close()


app = FastAPI(
    title="SchemeKnit API",
    description="Production Lesson Plan Generation for Ghanaian Teachers",
    version=settings.APP_VERSION,
    docs_url="/api/docs" if settings.DEBUG else None,
    openapi_url="/api/openapi.json" if settings.DEBUG else None,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    # Browsers hide non-safelisted response headers from JS unless they are
    # explicitly exposed. The download filename travels in a custom header
    # (see X_FILENAME_HEADER) so fetch()-based downloads keep working.
    expose_headers=["X-TeachFlow-Filename"],
)

from .security import RateLimitMiddleware, SecurityHeadersMiddleware
app.add_middleware(RateLimitMiddleware)
app.add_middleware(SecurityHeadersMiddleware)


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": True, "detail": exc.detail, "status_code": exc.status_code},
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    errors = []
    for error in exc.errors():
        field = " -> ".join(str(loc) for loc in error["loc"])
        errors.append({"field": field, "message": error["msg"]})
    return JSONResponse(
        status_code=422,
        content={"error": True, "detail": "Validation failed", "errors": errors},
    )


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    log_error("unhandled_exception", error=str(exc), path=str(request.url.path))
    return JSONResponse(
        status_code=500,
        content={"error": True, "detail": "Internal server error"},
    )


from .routers import documents, curriculum, generation, templates, settings as settings_router
from .routers import auth as auth_router
from .routers import payments as payments_router
from .routers import content_packs as content_packs_router
from .routers import ai_regeneration as ai_router
from .routers import platform_admin as platform_admin_router

app.include_router(auth_router.router, prefix="/api/auth", tags=["authentication"])
app.include_router(documents.router, prefix="/api/documents", tags=["documents"])
app.include_router(curriculum.router, prefix="/api/curriculum", tags=["curriculum"])
app.include_router(generation.router, prefix="/api/generation", tags=["generation"])
app.include_router(templates.router, prefix="/api/templates", tags=["templates"])
app.include_router(settings_router.router, prefix="/api/settings", tags=["settings"])
app.include_router(payments_router.router, prefix="/api/payments", tags=["payments"])
app.include_router(content_packs_router.router, prefix="/api/content-packs", tags=["content-packs"])
app.include_router(ai_router.router, prefix="/api/ai", tags=["ai"])
app.include_router(platform_admin_router.router, prefix="/api/platform-admin", tags=["platform-admin"])


@app.get("/api/health")
async def health_check():
    return {"status": "healthy", "service": "SchemeKnit", "version": settings.APP_VERSION}


@app.get("/api/ready")
async def readiness_check():
    """Readiness: process alive AND database + storage reachable.

    No secrets are exposed in the response.
    """
    checks = {}
    all_ok = True

    # Database
    try:
        from sqlalchemy import text
        db = SessionLocal()
        try:
            db.execute(text("SELECT 1"))
            checks["database"] = "reachable"
        finally:
            db.close()
    except Exception:
        checks["database"] = "unreachable"
        all_ok = False

    # Storage (local dir exists / S3 bucket reachable)
    try:
        from .storage import get_storage
        st = get_storage()
        if hasattr(st, "client"):
            # S3 — do a lightweight head-bucket
            st.client.head_bucket(Bucket=st.bucket)
        checks["storage"] = "reachable"
    except Exception:
        checks["storage"] = "unreachable"
        all_ok = False

    # Email (configuration present, not a live send)
    checks["email"] = "configured" if settings.RESEND_API_KEY else "not_configured"

    status_code = 200 if all_ok else 503
    return JSONResponse(
        status_code=status_code,
        content={
            "ready": all_ok,
            "service": "SchemeKnit",
            "version": settings.APP_VERSION,
            "checks": checks,
        },
    )


UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(exist_ok=True)
EXPORT_DIR = Path("exports")
EXPORT_DIR.mkdir(exist_ok=True)
TEMP_DIR = Path("temp")
TEMP_DIR.mkdir(exist_ok=True)
