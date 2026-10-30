"""Database URL normalization and Psycopg 3 driver-selection tests."""
from __future__ import annotations

import os
import sys

import pytest
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.database import normalize_database_url  # noqa: E402


def test_postgresql_scheme_selects_psycopg3():
    normalized = normalize_database_url(
        "postgresql://user:pass@db.example:5432/app?sslmode=require")
    assert normalized.startswith("postgresql+psycopg://")
    assert make_url(normalized).get_dialect().driver == "psycopg"
    assert make_url(normalized).database == "app"


def test_postgres_scheme_selects_psycopg3():
    normalized = normalize_database_url("postgres://user:pass@db.example/app")
    assert normalized.startswith("postgresql+psycopg://")
    assert make_url(normalized).get_dialect().driver == "psycopg"


def test_already_normalized_url_is_unchanged():
    value = "postgresql+psycopg://user:pass@db.example/app?sslmode=require"
    assert normalize_database_url(value) == value


def test_no_double_prefixing():
    value = "postgresql+psycopg://user:pass@db.example/app"
    assert normalize_database_url(normalize_database_url(value)) == value


def test_all_url_components_and_query_parameters_are_preserved():
    value = (
        "postgresql://app_user:p%40ss@db.example:6543/app_db"
        "?sslmode=require&channel_binding=require&application_name=teachflow"
    )
    normalized = normalize_database_url(value)
    original = make_url(value)
    result = make_url(normalized)
    assert result.username == original.username
    assert result.password == original.password
    assert result.host == original.host
    assert result.port == original.port
    assert result.database == original.database
    assert result.query["sslmode"] == "require"
    assert result.query["channel_binding"] == "require"
    assert result.query["application_name"] == "teachflow"


def test_sqlite_url_is_unchanged():
    for value in ("sqlite:///./teachflow.db", "sqlite:///:memory:"):
        assert normalize_database_url(value) == value


def test_other_explicit_driver_url_is_unchanged():
    value = "postgresql+some_driver://user:pass@db.example/app"
    assert normalize_database_url(value) == value


def test_empty_url_fails_without_echoing_a_secret():
    with pytest.raises(ValueError) as exc:
        normalize_database_url("")
    assert "DATABASE_URL" in str(exc.value)
    assert "pass" not in str(exc.value).lower()


def test_engine_resolves_psycopg3_without_connecting():
    normalized = normalize_database_url(
        "postgresql://user:pass@db.example:5432/app?sslmode=require")
    engine = create_engine(normalized)
    try:
        assert engine.dialect.driver == "psycopg"
        assert engine.dialect.name == "postgresql"
    finally:
        engine.dispose()
