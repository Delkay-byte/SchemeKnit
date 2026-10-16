#!/usr/bin/env python3
"""Disposable-PostgreSQL validation of the hardened quota-repair SQL
proposals in docs/QUOTA_ACCOUNTING_INCIDENT.md (Proposal 1 = §13e,
Proposal 2 = §13g).

Synthetic, production-shaped data only. Refuses any non-loopback host.
Creates and drops one scratch database per test case. Never touches
production. The repair/rollback scripts are extracted verbatim from the
document (markers `-- SCRIPT: P1-REPAIR` etc.), so the doc text is
exactly what gets executed.

State comparison uses a full-row LOGICAL fingerprint of every column of
every table in the synthetic repair schema (usage_units, usage_periods,
lesson_plans, generation_jobs): complete `to_jsonb(row)` representations
aggregated in primary-key order and md5-hashed. This is a logical
(row-content) fingerprint, not a physical database byte comparison.

Usage (from repo root):
    ./venv/Scripts/python backend/validate_quota_repair_sql.py
Env overrides: TEACHFLOW_QUOTA_CHECK_{HOST,PORT,USER,PASSWORD,DBNAME}
"""

from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path

import psycopg

DOC_PATH = Path(__file__).resolve().parents[1] / "docs" / "QUOTA_ACCOUNTING_INCIDENT.md"
LOOPBACK_HOSTS = {"127.0.0.1", "::1", "localhost"}

INC = "c11bde4c-a9bb-4f41-b96a-921570cf856e"
INC_SCHEME = "ab28233d-f87c-4753-98c1-fbb94acead7f"
INC_ORPHAN_CODE = "B9.1.1.2.1"
INC_ORPHAN_KEY = f"{INC_SCHEME}:{INC_ORPHAN_CODE}"
MID_TERM_CODE = "MID-TERM (05-11-2026 to 06-11-"  # 30 chars → key length 67
MID_ORPHAN_CREATED = "2026-09-26 15:30:23.633320"
INC_NEWEST = "2026-10-09 00:22:52.201720"

U_MID = "1474a7" + "0" * 30   # Sept 27 matched + 1 orphan, Oct 5 matched
U_42 = "2f62b5" + "0" * 30    # Sept 42 matched
U_O34 = "4995a6" + "0" * 30   # Oct 34 matched
U_O5A = "b2303e" + "0" * 30   # Oct 5 matched
U_O5B = "f801cf" + "0" * 30   # Oct 5 matched
SEPT5_USERS = [
    "2a9440" + "0" * 30,
    "2dbf6e" + "0" * 30,
    "5041ae" + "0" * 30,
    "762d46" + "0" * 30,
    "b03ee7" + "0" * 30,
    "bdadee" + "0" * 30,
    "dbe010" + "0" * 30,
    "206f1b" + "0" * 30,
]
JOB_OK = "dc22da" + "0" * 30

# Full-row logical fingerprint: every column of every table, complete
# to_jsonb(row) text, aggregated in primary-key order, md5-hashed.
FINGERPRINT_SQL = """
SELECT md5(
  (SELECT coalesce(string_agg(to_jsonb(u)::text, E'\\n' ORDER BY u.id), '')
     FROM usage_units u)
  || E'\\n#\\n' ||
  (SELECT coalesce(string_agg(to_jsonb(p)::text, E'\\n' ORDER BY p.id), '')
     FROM usage_periods p)
  || E'\\n#\\n' ||
  (SELECT coalesce(string_agg(to_jsonb(l)::text, E'\\n' ORDER BY l.id), '')
     FROM lesson_plans l)
  || E'\\n#\\n' ||
  (SELECT coalesce(string_agg(to_jsonb(j)::text, E'\\n' ORDER BY j.id), '')
     FROM generation_jobs j)
)
"""

AGGREGATE_SQL = """
SELECT (SELECT count(*) FROM usage_units),
       (SELECT coalesce(sum(units_used), 0) FROM usage_periods),
       (SELECT count(*) FROM usage_periods)
"""

SCHEMA_SQL = """
CREATE TABLE usage_periods (
  id text PRIMARY KEY,
  user_id text NOT NULL,
  period_type text NOT NULL,
  period_key text NOT NULL,
  units_used integer NOT NULL DEFAULT 0,
  created_at timestamp NOT NULL DEFAULT now(),
  updated_at timestamp NOT NULL DEFAULT now(),
  UNIQUE (user_id, period_type, period_key)
);
CREATE TABLE usage_units (
  id text PRIMARY KEY,
  user_id text NOT NULL,
  period_type text NOT NULL,
  period_key text NOT NULL,
  unit_kind text NOT NULL,
  unit_key text NOT NULL,
  scheme_id text,
  created_at timestamp NOT NULL DEFAULT now(),
  UNIQUE (user_id, period_type, period_key, unit_kind, unit_key)
);
CREATE INDEX ix_usage_units_period ON usage_units (user_id, period_type, period_key);
CREATE TABLE lesson_plans (
  id text PRIMARY KEY,
  owner_id text NOT NULL,
  scheme_id text NOT NULL,
  indicator_codes jsonb NOT NULL DEFAULT '[]'::jsonb,
  source_occurrence_id text DEFAULT '',
  job_id text NOT NULL
);
CREATE TABLE generation_jobs (
  id text PRIMARY KEY,
  owner_id text NOT NULL,
  status text NOT NULL,
  error_message text NOT NULL DEFAULT '',
  created_at timestamp NOT NULL DEFAULT now()
);
"""


def scheme_of(user: str) -> str:
    return (user + "0" * 36)[:36]


def seed_sql() -> tuple[str, dict]:
    """Deterministic production-shaped synthetic seed; all counters are 0.

    Every usage_periods row gets a deliberately DISTINCT original
    updated_at (recorded in meta['period_updated_at'] keyed by
    (user_id, period_key)) so a shared or newly generated timestamp can
    never accidentally match the expected restored state.
    """
    stmts: list[str] = []
    meta: dict = {"period_updated_at": {}}
    unit_n = 0
    period_n = 0

    def unit(user: str, period_key: str, scheme: str, code: str, created: str) -> None:
        nonlocal unit_n
        unit_n += 1
        stmts.append(
            "INSERT INTO usage_units (id, user_id, period_type, period_key,"
            " unit_kind, unit_key, scheme_id, created_at) VALUES ("
            f"'u{unit_n:04d}', '{user}', 'calendar_month', '{period_key}',"
            f" 'lesson_plan', '{scheme}:{code}', '{scheme}', '{created}');"
        )

    def lesson(lid: str, user: str, scheme: str, code: str, occ: str, job: str) -> None:
        codes = json.dumps([code])
        stmts.append(
            "INSERT INTO lesson_plans (id, owner_id, scheme_id, indicator_codes,"
            " source_occurrence_id, job_id) VALUES ("
            f"'{lid}', '{user}', '{scheme}', '{codes}'::jsonb, '{occ}', '{job}');"
        )

    def period(pid: str, user: str, key: str) -> None:
        nonlocal period_n
        period_n += 1
        ts = (
            datetime(2026, 9, 1, 8, 0, 0)
            + timedelta(minutes=17 * period_n, microseconds=123456 * period_n)
        ).strftime("%Y-%m-%d %H:%M:%S.%f")
        meta["period_updated_at"][(user, key)] = ts
        stmts.append(
            "INSERT INTO usage_periods (id, user_id, period_type, period_key,"
            f" units_used, created_at, updated_at) VALUES ('{pid}', '{user}',"
            f" 'calendar_month', '{key}', 0, '{ts}', '{ts}');"
        )

    def matched_group(user: str, key: str, count: int) -> None:
        scheme = scheme_of(user)
        month = int(key[5:7])
        for i in range(count):
            code = f"IND-{i:02d}"
            created = f"2026-{month:02d}-{(i % 27) + 1:02d} 09:00:00.000000"
            unit(user, key, scheme, code, created)
            lesson(
                f"l{user[:6]}{key[5:7]}{i:03d}", user, scheme, code,
                f"wk{i}:0:{code}", f"{user[:6]}job000",
            )

    inc_codes = [
        ("B9.1.1.1.1", "week1:0:B9.1.1.1.1", "2026-10-09 00:10:34.000000"),
        ("B9.1.1.1.2", "week2:0:B9.1.1.1.2", "2026-10-09 00:12:11.000000"),
        ("B9.1.1.1.3", "week2:1:B9.1.1.1.3", "2026-10-09 00:14:52.000000"),
        ("B9.1.2.1.1", "week4:0:B9.1.2.1.1", "2026-10-09 00:18:03.000000"),
        ("B9.1.2.1.2", "week4:1:B9.1.2.1.2", "2026-10-09 00:19:47.000000"),
        ("B9.1.2.1.3", "week5:0:B9.1.2.1.3", INC_NEWEST),
    ]
    for i, (code, occ, created) in enumerate(inc_codes, start=1):
        unit(INC, "2026-10", INC_SCHEME, code, created)
        lesson(f"li{i:03d}", INC, INC_SCHEME, code, occ, JOB_OK)
    unit(INC, "2026-10", INC_SCHEME, INC_ORPHAN_CODE, "2026-10-09 00:21:16.294309")
    period("pinc", INC, "2026-10")
    stmts.append(
        "INSERT INTO generation_jobs (id, owner_id, status, error_message,"
        f" created_at) VALUES ('{JOB_OK}', '{INC}', 'completed', '',"
        " '2026-10-09 00:09:00.000000');"
    )
    for j, t in enumerate(
        ["00:21:16.500000", "00:22:19.250000", "00:36:41.750000"], start=1
    ):
        stmts.append(
            "INSERT INTO generation_jobs (id, owner_id, status, error_message,"
            f" created_at) VALUES ('jf{j:02d}', '{INC}', 'failed', '',"
            f" '2026-10-09 {t}');"
        )
    for j in range(1, 7):
        stmts.append(
            "INSERT INTO generation_jobs (id, owner_id, status, error_message,"
            f" created_at) VALUES ('jx{j:02d}', '{INC}', 'completed', '',"
            f" '2026-10-08 1{j}:00:00.000000');"
        )

    period("pmid09", U_MID, "2026-09")
    period("pmid10", U_MID, "2026-10")
    matched_group(U_MID, "2026-09", 27)
    matched_group(U_MID, "2026-10", 5)
    unit(U_MID, "2026-09", scheme_of(U_MID), MID_TERM_CODE, MID_ORPHAN_CREATED)
    period("p42", U_42, "2026-09")
    matched_group(U_42, "2026-09", 42)
    period("po34", U_O34, "2026-10")
    matched_group(U_O34, "2026-10", 34)
    for u, pid in [(U_O5A, "po5a"), (U_O5B, "po5b")]:
        period(pid, u, "2026-10")
        matched_group(u, "2026-10", 5)
    for i, u in enumerate(SEPT5_USERS):
        period(f"ps5{i}", u, "2026-09")
        matched_group(u, "2026-09", 5)
    assert period_n == 15, f"expected 15 period rows, built {period_n}"
    return "\n".join(stmts), meta


def split_statements(sql: str) -> list[str]:
    """Split SQL on ';' at depth 0; dollar-quote/comment/string aware."""
    stmts: list[str] = []
    buf: list[str] = []
    i, n = 0, len(sql)
    dollar: str | None = None
    in_single = in_line = in_block = False
    while i < n:
        c = sql[i]
        if in_line:
            buf.append(c)
            if c == "\n":
                in_line = False
            i += 1
            continue
        if in_block:
            buf.append(c)
            if sql.startswith("*/", i):
                buf.append("/")
                in_block = False
                i += 2
                continue
            i += 1
            continue
        if in_single:
            buf.append(c)
            if c == "'":
                if sql.startswith("''", i):
                    buf.append("'")
                    i += 2
                    continue
                in_single = False
            i += 1
            continue
        if dollar is not None:
            if sql.startswith(dollar, i):
                buf.append(dollar)
                i += len(dollar)
                dollar = None
                continue
            buf.append(c)
            i += 1
            continue
        if sql.startswith("--", i):
            in_line = True
            buf.append(c)
            i += 1
            continue
        if sql.startswith("/*", i):
            in_block = True
            buf.append(c)
            i += 1
            continue
        if c == "'":
            in_single = True
            buf.append(c)
            i += 1
            continue
        m = re.match(r"\$[A-Za-z_0-9]*\$", sql[i:])
        if m:
            dollar = m.group(0)
            buf.append(dollar)
            i += len(dollar)
            continue
        if c == ";":
            stmt = "".join(buf).strip()
            if stmt:
                stmts.append(stmt)
            buf = []
            i += 1
            continue
        buf.append(c)
        i += 1
    tail = "".join(buf).strip()
    if tail:
        stmts.append(tail)
    return stmts


def extract_script(doc_text: str, marker: str) -> str:
    """Extract the fenced sql block containing the given marker comment.

    Line-based fence walk: an opening fence is a line that strips to
    '```sql'; the next line that strips to '```' closes it.
    """
    lines = doc_text.splitlines()
    i = 0
    while i < len(lines):
        if lines[i].strip() == "```sql":
            j = i + 1
            while j < len(lines) and lines[j].strip() != "```":
                j += 1
            block = "\n".join(lines[i + 1:j])
            if f"-- SCRIPT: {marker}" in block:
                return block
            i = j + 1
            continue
        i += 1
    raise SystemExit(f"FATAL: marker '-- SCRIPT: {marker}' not found in {DOC_PATH}")


MUTATING = re.compile(r"^\s*(INSERT|UPDATE|DELETE)\b", re.I)
ALLOWED_TARGETS = {"usage_units", "usage_periods"}


def check_repair_scope(name: str, script: str) -> None:
    """Top-level mutating statements must only target usage tables."""
    for stmt in split_statements(script):
        if not MUTATING.match(stmt):
            continue
        tables = set(re.findall(r"\b(?:FROM|INTO|UPDATE)\s+([a-z_]+)", stmt, re.I))
        bad = {t for t in tables if t not in ALLOWED_TARGETS}
        if bad:
            raise SystemExit(f"FATAL: {name} mutates non-allowlisted tables: {bad}")


class Fail(Exception):
    pass


def expect(cond: bool, msg: str) -> None:
    if not cond:
        raise Fail(msg)


def expect_sqlstate(err: Exception | None, code: str) -> None:
    if err is None:
        raise Fail(f"expected abort with sqlstate {code}, but script committed")
    state = getattr(err, "sqlstate", None)
    if state != code:
        raise Fail(f"expected sqlstate {code}, got {state!r}: {err}")


def parse_deleted(notices: list[str], p2: bool) -> dict[str, str]:
    for n in notices:
        if not n.startswith("DELETED_ORPHAN"):
            continue
        if p2:
            m = re.match(
                r"DELETED_ORPHAN id=(\S+) user=(\S+) scheme=(\S+) key=(.*)"
                r" created_at=(.+)$", n,
            )
            assert m, f"unparseable P2 packet: {n}"
            return {
                "id": m.group(1), "user": m.group(2), "scheme": m.group(3),
                "key": m.group(4), "created_at": m.group(5).strip(),
            }
        m = re.match(r"DELETED_ORPHAN id=(\S+) key=(\S+) created_at=(.+)$", n)
        assert m, f"unparseable P1 packet: {n}"
        return {"id": m.group(1), "key": m.group(2), "created_at": m.group(3).strip()}
    raise AssertionError(f"no DELETED_ORPHAN notice; got {notices}")


def parse_ts(notices: list[str]) -> str:
    for n in notices:
        if n.startswith("REPAIRED_TS "):
            return n[len("REPAIRED_TS "):].strip()
    raise AssertionError(f"no REPAIRED_TS notice; got {notices}")


def parse_p1_original(notices: list[str]) -> dict[str, str]:
    for n in notices:
        if n.startswith("P1_ORIGINAL_PERIOD "):
            m = re.match(
                r"P1_ORIGINAL_PERIOD user_id=(\S+) period_key=(\S+)"
                r" updated_at=(.+)$", n,
            )
            assert m, f"unparseable P1_ORIGINAL_PERIOD packet: {n}"
            return {
                "user_id": m.group(1), "period_key": m.group(2),
                "updated_at": m.group(3).strip(),
            }
    raise AssertionError(f"no P1_ORIGINAL_PERIOD notice; got {notices}")


def parse_p2_original(notices: list[str]) -> list[tuple[str, str, str, str]]:
    rows: list[tuple[str, str, str, str]] = []
    for n in notices:
        if n.startswith("P2_ORIGINAL_PERIOD "):
            m = re.match(
                r"P2_ORIGINAL_PERIOD user_id=(\S+) period_type=(\S+)"
                r" period_key=(\S+) updated_at=(.+)$", n,
            )
            assert m, f"unparseable P2_ORIGINAL_PERIOD packet: {n}"
            rows.append((m.group(1), m.group(2), m.group(3), m.group(4).strip()))
    assert len(rows) == 14, f"expected 14 P2_ORIGINAL_PERIOD notices, got {len(rows)}"
    return rows


def p2_values_list(rows: list[tuple[str, str, str, str]]) -> str:
    return ", ".join(
        f"('{u}','{pt}','{pk}','{ts}')" for u, pt, pk, ts in rows
    )


def substitute(sql: str, mapping: dict[str, str]) -> str:
    for k, v in mapping.items():
        sql = sql.replace(f"<{k}>", v)
    return sql


class Runner:
    def __init__(self, doc_text: str) -> None:
        host = os.environ.get("TEACHFLOW_QUOTA_CHECK_HOST", "127.0.0.1")
        if host not in LOOPBACK_HOSTS:
            raise SystemExit(
                f"FATAL: refusing non-loopback host {host!r}"
                " (synthetic scratch DBs only)"
            )
        self.host = host
        self.port = int(os.environ.get("TEACHFLOW_QUOTA_CHECK_PORT", "54329"))
        self.user = os.environ.get("TEACHFLOW_QUOTA_CHECK_USER", "schemeknit")
        self.password = os.environ.get(
            "TEACHFLOW_QUOTA_CHECK_PASSWORD", "quota_test_pw"
        )
        self.maint_db = os.environ.get("TEACHFLOW_QUOTA_CHECK_DBNAME", "postgres")
        self.scripts = {
            name: extract_script(doc_text, name)
            for name in ("P1-REPAIR", "P1-ROLLBACK", "P2-REPAIR", "P2-ROLLBACK")
        }
        check_repair_scope("P1-REPAIR", self.scripts["P1-REPAIR"])
        check_repair_scope("P2-REPAIR", self.scripts["P2-REPAIR"])
        self.seed, self.seed_meta = seed_sql()
        assert len(MID_TERM_CODE) == 30, "MID-TERM code must be 30 chars"
        assert len(scheme_of(U_MID)) + 1 + len(MID_TERM_CODE) == 67
        # seed timestamps must be distinct across all 15 period rows
        ts_list = list(self.seed_meta["period_updated_at"].values())
        assert len(set(ts_list)) == 15, "seed period updated_at values must be distinct"

    def _conn(self, dbname: str):
        return psycopg.connect(
            host=self.host, port=self.port, dbname=dbname,
            user=self.user, password=self.password, autocommit=True,
        )

    def scratch(self, dbname: str) -> None:
        with self._conn(self.maint_db) as c:
            c.execute(f'DROP DATABASE IF EXISTS "{dbname}"')
            c.execute(f'CREATE DATABASE "{dbname}"')

    def drop(self, dbname: str) -> None:
        with self._conn(self.maint_db) as c:
            c.execute(
                "SELECT pg_terminate_backend(pid) FROM pg_stat_activity"
                f" WHERE datname = '{dbname}' AND pid <> pg_backend_pid()"
            )
            c.execute(f'DROP DATABASE IF EXISTS "{dbname}"')

    def seed_fresh(self, dbname: str):
        self.scratch(dbname)
        conn = self._conn(dbname)
        with conn.cursor() as cur:
            cur.execute(SCHEMA_SQL)
            cur.execute(self.seed)
        return conn

    def run_script(self, conn, name: str, sql: str | None = None):
        """Run a doc script statement-by-statement on an autocommit connection
        (the script's own BEGIN/COMMIT control the transaction). Stops at the
        first error and rolls back. Returns (notices, error|None)."""
        notices: list[str] = []
        conn.add_notice_handler(
            lambda diag, sink=notices: sink.append(diag.message_primary)
        )
        body = self.scripts[name] if sql is None else sql
        error: Exception | None = None
        with conn.cursor() as cur:
            for stmt in split_statements(body):
                try:
                    cur.execute(stmt)
                except Exception as e:  # noqa: BLE001 — recorded, then stop
                    error = e
                    break
        if error is not None:
            try:
                with conn.cursor() as cur:
                    cur.execute("ROLLBACK")
            except Exception:  # noqa: BLE001
                pass
        return notices, error

    def fingerprint(self, conn) -> str:
        return self.one(conn, FINGERPRINT_SQL)[0]

    def aggregates(self, conn):
        return tuple(self.one(conn, AGGREGATE_SQL))

    def one(self, conn, sql: str, args=None):
        with conn.cursor() as cur:
            cur.execute(sql, args)
            return cur.fetchone()

    def rows(self, conn, sql: str) -> list:
        with conn.cursor() as cur:
            cur.execute(sql)
            return [list(row) for row in cur.fetchall()]

    def exec(self, conn, sql: str) -> None:
        with conn.cursor() as cur:
            cur.execute(sql)

    def p1_packets(self, notices: list[str]) -> dict[str, str]:
        packet = parse_deleted(notices, p2=False)
        packet["repaired_ts"] = parse_ts(notices)
        packet.update(parse_p1_original(notices))
        return packet

    def p2_packets(self, notices: list[str]) -> dict:
        packet = parse_deleted(notices, p2=True)
        packet["repaired_ts"] = parse_ts(notices)
        packet["originals"] = parse_p2_original(notices)
        return packet


def run_all() -> int:
    doc_text = DOC_PATH.read_text(encoding="utf-8")
    r = Runner(doc_text)
    results: list[tuple[str, bool, str]] = []
    dbname = "quota_rep_check"
    orig_meta: dict = r.seed_meta["period_updated_at"]

    def case(name: str, fn) -> None:
        try:
            fn(dbname)
            results.append((name, True, ""))
        except Fail as e:
            results.append((name, False, str(e)))
        except Exception as e:  # noqa: BLE001
            results.append((name, False, f"{type(e).__name__}: {e}"))
        finally:
            r.drop(dbname)

    def sub_p1(packet: dict[str, str]) -> dict[str, str]:
        return {
            "ORPHAN_ID": packet["id"],
            "ORPHAN_CREATED_AT": packet["created_at"],
            "REPAIRED_TS": packet["repaired_ts"],
            "ORIGINAL_PERIOD_TS": packet["updated_at"],
        }

    def sub_p2(packet: dict) -> dict[str, str]:
        return {
            "ORPHAN_ID": packet["id"],
            "ORPHAN_USER_ID": packet["user"],
            "ORPHAN_SCHEME_ID": packet["scheme"],
            "ORPHAN_UNIT_KEY": packet["key"],
            "ORPHAN_CREATED_AT": packet["created_at"],
            "REPAIRED_TS": packet["repaired_ts"],
            "P2_ORIGINAL_PERIODS": p2_values_list(packet["originals"]),
        }

    def original_ts(user: str, key: str) -> datetime:
        return datetime.fromisoformat(orig_meta[(user, key)])

    # 1 — P1 repair valid; all three packets emitted ----------------------
    def case1(db: str) -> None:
        conn = r.seed_fresh(db)
        notices, err = r.run_script(conn, "P1-REPAIR")
        expect(err is None, f"P1-REPAIR failed: {err}")
        packet = r.p1_packets(notices)
        expect(packet["key"] == INC_ORPHAN_KEY, f"wrong key {packet['key']}")
        expect(packet["user_id"] == INC and packet["period_key"] == "2026-10",
               f"unexpected P1_ORIGINAL_PERIOD identity: {packet}")
        expect(
            datetime.fromisoformat(packet["updated_at"])
            == original_ts(INC, "2026-10"),
            "P1_ORIGINAL_PERIOD ts does not match the seed's original value",
        )
        expect(r.one(conn, f"SELECT count(*) FROM usage_units WHERE user_id='{INC}'")[0] == 6,
               "incident units != 6")
        expect(r.one(conn, f"SELECT units_used FROM usage_periods WHERE user_id='{INC}'")[0] == 6,
               "incident counter != 6")
        conn.close()

    # 2 — P1 rollback restores the complete original full-row fingerprint --
    def case2(db: str) -> None:
        conn = r.seed_fresh(db)
        fp0 = r.fingerprint(conn)
        notices, err = r.run_script(conn, "P1-REPAIR")
        expect(err is None, f"P1-REPAIR failed: {err}")
        packet = r.p1_packets(notices)
        rb = substitute(r.scripts["P1-ROLLBACK"], sub_p1(packet))
        _, err = r.run_script(conn, "P1-ROLLBACK", sql=rb)
        expect(err is None, f"P1-ROLLBACK failed: {err}")
        expect(r.fingerprint(conn) == fp0,
               "P1 rollback did not restore the complete original fingerprint")
        restored_ts = r.one(conn, (
            f"SELECT updated_at FROM usage_periods WHERE user_id='{INC}'"
            " AND period_key='2026-10'"
        ))[0]
        expect(restored_ts == original_ts(INC, "2026-10"),
               f"incident period updated_at not restored: {restored_ts}")
        conn.close()

    # 3 — P2 repair valid; 14 distinct original-period packets ------------
    def case3(db: str) -> None:
        conn = r.seed_fresh(db)
        notices, err = r.run_script(conn, "P2-REPAIR")
        expect(err is None, f"P2-REPAIR failed: {err}")
        packet = r.p2_packets(notices)
        identities = {(u, pt, pk) for u, pt, pk, _ in packet["originals"]}
        expect(len(identities) == 14, "P2 original-period packets not distinct")
        expected = {(u, "calendar_month", k) for (u, k) in orig_meta if u != INC}
        expect(identities == expected,
               f"packet identities do not match the 14 non-incident rows: {identities ^ expected}")
        for u, pt, pk, ts in packet["originals"]:
            expect(datetime.fromisoformat(ts) == original_ts(u, pk),
                   f"captured original ts mismatch for {u}/{pk}")
        sept = [row[0] for row in r.rows(conn, (
            f"SELECT units_used FROM usage_periods WHERE user_id<>'{INC}'"
            " AND period_key='2026-09' ORDER BY units_used"))]
        oct_ = [row[0] for row in r.rows(conn, (
            f"SELECT units_used FROM usage_periods WHERE user_id<>'{INC}'"
            " AND period_key='2026-10' ORDER BY units_used"))]
        expect(sept == [5, 5, 5, 5, 5, 5, 5, 5, 27, 42], f"Sept counters {sept}")
        expect(oct_ == [5, 5, 5, 34], f"Oct counters {oct_}")
        expect(r.one(conn, f"SELECT count(*) FROM usage_units WHERE user_id<>'{INC}'")[0] == 158,
               "non-incident units != 158")
        conn.close()

    # 4 — P2 rollback restores the complete original full-row fingerprint --
    def case4(db: str) -> None:
        conn = r.seed_fresh(db)
        fp0 = r.fingerprint(conn)
        notices, err = r.run_script(conn, "P2-REPAIR")
        expect(err is None, f"P2-REPAIR failed: {err}")
        packet = r.p2_packets(notices)
        rb = substitute(r.scripts["P2-ROLLBACK"], sub_p2(packet))
        _, err = r.run_script(conn, "P2-ROLLBACK", sql=rb)
        expect(err is None, f"P2-ROLLBACK failed: {err}")
        expect(r.fingerprint(conn) == fp0,
               "P2 rollback did not restore the complete original fingerprint")
        for u, pt, pk, _ in packet["originals"]:
            restored = r.one(conn, (
                "SELECT updated_at FROM usage_periods"
                f" WHERE user_id='{u}' AND period_key='{pk}'"
            ))[0]
            expect(restored == original_ts(u, pk),
                   f"updated_at not restored for {u}/{pk}: {restored}")
        conn.close()

    # 5 — both execution orders converge ----------------------------------
    def case5(db: str) -> None:
        finals = []
        for order in (["P1-REPAIR", "P2-REPAIR"], ["P2-REPAIR", "P1-REPAIR"]):
            conn = r.seed_fresh(db)
            for name in order:
                _, err = r.run_script(conn, name)
                expect(err is None, f"{name} failed in order {order}: {err}")
            state = tuple(r.one(conn, (
                "SELECT (SELECT count(*) FROM usage_units),"
                " (SELECT sum(units_used) FROM usage_periods),"
                f" (SELECT units_used FROM usage_periods WHERE user_id='{INC}'"
                "  AND period_key='2026-10')"
            )))
            finals.append(state)
            conn.close()
        expect(finals[0] == finals[1] == (164, 164, 6), f"orders diverged: {finals}")

    # 6 — precondition aborts; full fingerprint unchanged after each ------
    def case6(db: str) -> None:
        scenarios = [
            ("P1-REPAIR", f"UPDATE usage_periods SET units_used=1 WHERE user_id='{INC}'"),
            ("P1-REPAIR", f"DELETE FROM usage_units WHERE unit_key='{INC_ORPHAN_KEY}'"),
            ("P2-REPAIR", f"UPDATE usage_periods SET units_used=1 WHERE user_id='{U_42}'"),
            ("P2-REPAIR", f"DELETE FROM usage_units WHERE created_at='{MID_ORPHAN_CREATED}'"),
        ]
        for script, tamper in scenarios:
            conn = r.seed_fresh(db)
            r.exec(conn, tamper)
            fp = r.fingerprint(conn)
            _, err = r.run_script(conn, script)
            expect_sqlstate(err, "TP001")
            expect(r.fingerprint(conn) == fp, f"DB changed after refused {script} ({tamper[:40]})")
            conn.close()
        # extra orphan
        conn = r.seed_fresh(db)
        r.exec(conn, (
            "INSERT INTO usage_units (id, user_id, period_type, period_key,"
            " unit_kind, unit_key, scheme_id, created_at) VALUES"
            f" ('xtra1','{INC}','calendar_month','2026-10','lesson_plan',"
            f" '{INC_SCHEME}:EXTRA-1','{INC_SCHEME}','2026-10-01 08:00:00')"
        ))
        fp = r.fingerprint(conn)
        _, err = r.run_script(conn, "P1-REPAIR")
        expect_sqlstate(err, "TP001")
        expect(r.fingerprint(conn) == fp, "DB changed after refused P1 (extra orphan)")
        conn.close()
        conn = r.seed_fresh(db)
        r.exec(conn, (
            "INSERT INTO usage_units (id, user_id, period_type, period_key,"
            " unit_kind, unit_key, scheme_id, created_at) VALUES"
            f" ('xtra2','{U_42}','calendar_month','2026-09','lesson_plan',"
            f" '{scheme_of(U_42)}:EXTRA-2','{scheme_of(U_42)}','2026-09-05 08:00:00')"
        ))
        fp = r.fingerprint(conn)
        _, err = r.run_script(conn, "P2-REPAIR")
        expect_sqlstate(err, "TP001")
        expect(r.fingerprint(conn) == fp, "DB changed after refused P2 (extra orphan)")
        conn.close()
        # changed orphan identity
        conn = r.seed_fresh(db)
        r.exec(conn, (
            "UPDATE usage_units SET created_at='2026-10-09 00:21:17.000000'"
            f" WHERE unit_key='{INC_ORPHAN_KEY}'"
        ))
        fp = r.fingerprint(conn)
        _, err = r.run_script(conn, "P1-REPAIR")
        expect_sqlstate(err, "TP001")
        expect(r.fingerprint(conn) == fp, "DB changed after refused P1 (changed identity)")
        conn.close()
        conn = r.seed_fresh(db)
        r.exec(conn, (
            "UPDATE usage_units SET unit_key = unit_key || 'X'"
            f" WHERE created_at='{MID_ORPHAN_CREATED}'"
        ))
        fp = r.fingerprint(conn)
        _, err = r.run_script(conn, "P2-REPAIR")
        expect_sqlstate(err, "TP001")
        expect(r.fingerprint(conn) == fp, "DB changed after refused P2 (changed identity)")
        conn.close()

    # 7 — tampered scripts abort; no partial commit -----------------------
    def case7(db: str) -> None:
        conn = r.seed_fresh(db)
        tampered = r.scripts["P1-REPAIR"].replace(
            "-- B2: repaired counter",
            "DELETE FROM usage_units WHERE id = 'u0001';\n  -- B2: repaired counter",
            1,
        )
        expect(tampered != r.scripts["P1-REPAIR"], "P1 tamper anchor not found")
        fp = r.fingerprint(conn)
        _, err = r.run_script(conn, "P1-REPAIR", sql=tampered)
        expect_sqlstate(err, "TP002")
        expect(r.fingerprint(conn) == fp, "partial commit leaked after tampered P1")
        conn.close()
        conn = r.seed_fresh(db)
        tampered = r.scripts["P2-REPAIR"].replace(
            "-- B2: recompute all 14",
            "DELETE FROM usage_units WHERE id = 'u0001';\n  -- B2: recompute all 14",
            1,
        )
        expect(tampered != r.scripts["P2-REPAIR"], "P2 tamper anchor not found")
        fp = r.fingerprint(conn)
        _, err = r.run_script(conn, "P2-REPAIR", sql=tampered)
        expect_sqlstate(err, "TP002")
        expect(r.fingerprint(conn) == fp, "partial commit leaked after tampered P2")
        conn.close()

    # 8 — rollback refuses after intervening activity; DB unchanged -------
    def case8(db: str) -> None:
        conn = r.seed_fresh(db)
        notices, err = r.run_script(conn, "P1-REPAIR")
        expect(err is None, f"P1-REPAIR failed: {err}")
        packet = r.p1_packets(notices)
        r.exec(conn, (
            "INSERT INTO usage_units (id, user_id, period_type, period_key,"
            " unit_kind, unit_key, scheme_id, created_at) VALUES"
            f" ('act1','{INC}','calendar_month','2026-10','lesson_plan',"
            f" '{INC_SCHEME}:NEW-ACT','{INC_SCHEME}', now())"
        ))
        r.exec(conn, f"UPDATE usage_periods SET units_used=7 WHERE user_id='{INC}'")
        fp = r.fingerprint(conn)
        rb = substitute(r.scripts["P1-ROLLBACK"], sub_p1(packet))
        _, err = r.run_script(conn, "P1-ROLLBACK", sql=rb)
        expect_sqlstate(err, "TP003")
        expect(r.fingerprint(conn) == fp, "refused P1 rollback modified the DB")
        conn.close()
        conn = r.seed_fresh(db)
        notices, err = r.run_script(conn, "P2-REPAIR")
        expect(err is None, f"P2-REPAIR failed: {err}")
        packet = r.p2_packets(notices)
        r.exec(conn, f"UPDATE usage_periods SET units_used=6 WHERE user_id='{U_O34}'")
        fp = r.fingerprint(conn)
        rb = substitute(r.scripts["P2-ROLLBACK"], sub_p2(packet))
        _, err = r.run_script(conn, "P2-ROLLBACK", sql=rb)
        expect_sqlstate(err, "TP003")
        expect(r.fingerprint(conn) == fp, "refused P2 rollback (activity) modified the DB")
        conn.close()

    # 9 — rollback refuses after counter / repair-timestamp drift ---------
    def case9(db: str) -> None:
        # P1: repair-timestamp drift only (counter still 6)
        conn = r.seed_fresh(db)
        notices, err = r.run_script(conn, "P1-REPAIR")
        expect(err is None, f"P1-REPAIR failed: {err}")
        packet = r.p1_packets(notices)
        r.exec(conn, (
            "UPDATE usage_periods SET updated_at = updated_at + interval '1 second'"
            f" WHERE user_id='{INC}'"
        ))
        fp = r.fingerprint(conn)
        rb = substitute(r.scripts["P1-ROLLBACK"], sub_p1(packet))
        _, err = r.run_script(conn, "P1-ROLLBACK", sql=rb)
        expect_sqlstate(err, "TP003")
        expect(r.fingerprint(conn) == fp, "refused P1 rollback (ts drift) modified the DB")
        conn.close()
        # P2: counter drift
        conn = r.seed_fresh(db)
        notices, err = r.run_script(conn, "P2-REPAIR")
        expect(err is None, f"P2-REPAIR failed: {err}")
        packet = r.p2_packets(notices)
        r.exec(conn, f"UPDATE usage_periods SET units_used=6 WHERE user_id='{U_O34}'")
        fp = r.fingerprint(conn)
        rb = substitute(r.scripts["P2-ROLLBACK"], sub_p2(packet))
        _, err = r.run_script(conn, "P2-ROLLBACK", sql=rb)
        expect_sqlstate(err, "TP003")
        expect(r.fingerprint(conn) == fp, "refused P2 rollback (counter drift) modified the DB")
        conn.close()
        # P2: repair-timestamp drift only
        conn = r.seed_fresh(db)
        notices, err = r.run_script(conn, "P2-REPAIR")
        expect(err is None, f"P2-REPAIR failed: {err}")
        packet = r.p2_packets(notices)
        r.exec(conn, (
            "UPDATE usage_periods SET updated_at = updated_at + interval '1 second'"
            f" WHERE user_id='{U_O5A}'"
        ))
        fp = r.fingerprint(conn)
        rb = substitute(r.scripts["P2-ROLLBACK"], sub_p2(packet))
        _, err = r.run_script(conn, "P2-ROLLBACK", sql=rb)
        expect_sqlstate(err, "TP003")
        expect(r.fingerprint(conn) == fp, "refused P2 rollback (ts drift) modified the DB")
        conn.close()

    # 10 — rollback refuses on a bad captured packet; DB unchanged --------
    def case10(db: str) -> None:
        # duplicated capture entry (15 rows)
        conn = r.seed_fresh(db)
        notices, err = r.run_script(conn, "P2-REPAIR")
        expect(err is None, f"P2-REPAIR failed: {err}")
        packet = r.p2_packets(notices)
        values = p2_values_list(packet["originals"])
        rb = substitute(r.scripts["P2-ROLLBACK"], sub_p2(packet))
        rb = rb.replace(values, values + ", " + values.split(", ", 1)[0], 1)
        fp = r.fingerprint(conn)
        _, err = r.run_script(conn, "P2-ROLLBACK", sql=rb)
        expect_sqlstate(err, "TP003")
        expect(r.fingerprint(conn) == fp, "refused P2 rollback (dup capture) modified the DB")
        conn.close()
        # missing capture entry (13 rows)
        conn = r.seed_fresh(db)
        notices, err = r.run_script(conn, "P2-REPAIR")
        expect(err is None, f"P2-REPAIR failed: {err}")
        packet = r.p2_packets(notices)
        values = p2_values_list(packet["originals"])
        rb = substitute(r.scripts["P2-ROLLBACK"], sub_p2(packet))
        rb = rb.replace(values, ", ".join(values.split(", ")[:2]), 1)
        fp = r.fingerprint(conn)
        _, err = r.run_script(conn, "P2-ROLLBACK", sql=rb)
        expect_sqlstate(err, "TP003")
        expect(r.fingerprint(conn) == fp, "refused P2 rollback (missing capture) modified the DB")
        conn.close()
        # wrong identity (14 distinct entries, one does not match a row)
        conn = r.seed_fresh(db)
        notices, err = r.run_script(conn, "P2-REPAIR")
        expect(err is None, f"P2-REPAIR failed: {err}")
        packet = r.p2_packets(notices)
        mutated = list(packet["originals"])
        u, pt, pk, ts = mutated[0]
        mutated[0] = (u, pt, "2099-12", ts)
        rb = substitute(r.scripts["P2-ROLLBACK"], sub_p2({**packet, "originals": mutated}))
        fp = r.fingerprint(conn)
        _, err = r.run_script(conn, "P2-ROLLBACK", sql=rb)
        expect_sqlstate(err, "TP003")
        expect(r.fingerprint(conn) == fp, "refused P2 rollback (wrong identity) modified the DB")
        conn.close()

    # 11 — fingerprint sensitivity: omitted-by-count fields change it -----
    def case11(db: str) -> None:
        mutations = [
            "UPDATE usage_units SET created_at = created_at + interval '1 second' WHERE id = 'u0001'",
            f"UPDATE usage_units SET scheme_id = 'deadbeef00' WHERE id = 'u0001'",
            "UPDATE usage_periods SET updated_at = updated_at + interval '1 second' WHERE id = 'pinc'",
        ]
        for sql in mutations:
            conn = r.seed_fresh(db)
            fp0 = r.fingerprint(conn)
            agg0 = r.aggregates(conn)
            r.exec(conn, sql)
            fp1 = r.fingerprint(conn)
            agg1 = r.aggregates(conn)
            expect(fp1 != fp0, f"fingerprint did not change after: {sql}")
            expect(agg0 == agg1,
                   f"aggregates changed (unexpected) after: {sql}: {agg0} vs {agg1}")
            conn.close()

    case("1  P1 repair valid + 3 packets", case1)
    case("2  P1 rollback restores full fingerprint", case2)
    case("3  P2 repair valid + 14 packets", case3)
    case("4  P2 rollback restores full fingerprint", case4)
    case("5  both orders converge", case5)
    case("6  precondition aborts, fingerprint unchanged", case6)
    case("7  tampered scripts abort, no partial commit", case7)
    case("8  rollback refuses after activity", case8)
    case("9  rollback refuses after counter/ts drift", case9)
    case("10 rollback refuses on bad captured packet", case10)
    case("11 fingerprint sensitive to every column", case11)

    width = max(len(name) for name, _, _ in results)
    print(f"Doc: {DOC_PATH}")
    print(f"Host: {r.host}:{r.port}  user={r.user}  (scratch DB per case, dropped after)")
    print("Fingerprint: full-row logical (all columns of usage_units,")
    print("  usage_periods, lesson_plans, generation_jobs; to_jsonb per row,")
    print("  aggregated in primary-key order, md5)")
    print()
    failed = 0
    for name, ok, detail in results:
        line = f"  [{'PASS' if ok else 'FAIL'}] {name.ljust(width)}"
        if detail:
            line += f"  — {detail}"
        print(line)
        if not ok:
            failed += 1
    print()
    print(f"{len(results) - failed}/{len(results)} cases passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(run_all())
