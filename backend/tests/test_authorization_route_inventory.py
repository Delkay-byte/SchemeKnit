"""Route inventory: sensitive handlers must declare an auth dependency."""
from __future__ import annotations

import importlib
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))

AUTH_DEPS = {
    "get_current_user", "require_teacher_workflow", "require_admin",
    "require_platform_admin", "require_valid_license",
}

# Genuinely public catalogue/auth/bootstrap routes.
PUBLIC = {
    ("auth", "/setup/status", "GET"),
    ("auth", "/setup", "POST"),
    ("auth", "/activation/validate", "POST"),
    ("auth", "/setup-school-admin", "POST"),
    ("auth", "/login", "POST"),
    ("auth", "/register/individual", "POST"),
    ("auth", "/setup-platform-admin/status", "GET"),
    ("auth", "/setup-platform-admin", "POST"),
    ("auth", "/reset-token/validate", "GET"),
    ("auth", "/confirm-password-reset", "POST"),
    ("templates", "/profiles", "GET"),
    ("templates", "/profiles/{educational_level}", "GET"),
    ("templates", "/{template_id}", "GET"),
    ("templates", "/legacy/{template_type}", "GET"),
    ("settings", "/subjects", "GET"),
    ("settings", "/subjects/by-level", "GET"),
    ("settings", "/class-levels", "GET"),
    ("settings", "/educational-levels", "GET"),
    ("settings", "/template-types", "GET"),
    ("settings", "/ai-modes", "GET"),
    ("settings", "/ai-status", "GET"),
    ("settings", "/teaching-days", "GET"),
    ("ai_regeneration", "/sections", "GET"),
    ("platform_admin", "/activate", "POST"),
    ("generation", "/downloads/{token}", "GET"),
    ("payments", "/config", "GET"),
    ("payments", "/plans", "GET"),
}

MODULES = (
    "documents", "curriculum", "generation", "templates", "weekly_plans",
    "settings", "ai_regeneration", "platform_admin", "payments",
)


def _routes(module: str):
    mod = importlib.import_module(f"src.routers.{module}")
    for route in getattr(mod.router, "routes", []):
        path = getattr(route, "path", "")
        methods = getattr(route, "methods", set()) or set()
        deps = [
            getattr(dep.call, "__name__", str(dep.call))
            for dep in (getattr(route, "dependant", None).dependencies
                        if getattr(route, "dependant", None) else [])
        ]
        yield path, methods, deps


def test_sensitive_handlers_declare_authentication():
    missing = []
    checked = 0
    for module in MODULES:
        for path, methods, deps in _routes(module):
            for method in methods:
                key = (module, path, method)
                if method in ("HEAD", "OPTIONS"):
                    continue
                if key in PUBLIC:
                    continue
                checked += 1
                if not (set(deps) & AUTH_DEPS):
                    missing.append(key)
    assert checked >= 80, checked
    assert missing == [], missing


def test_platform_admin_handlers_require_platform_admin():
    missing = []
    for path, methods, deps in _routes("platform_admin"):
        for method in methods:
            if (("platform_admin", path, method) in PUBLIC
                    or method in ("HEAD", "OPTIONS")):
                continue
            if "require_platform_admin" not in deps:
                missing.append((path, method, deps))
    assert missing == [], missing
