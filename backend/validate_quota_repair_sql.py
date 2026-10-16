#!/usr/bin/env python3
"""Disposable-PostgreSQL validation of the hardened quota-repair SQL
proposals in docs/QUOTA_ACCOUNTING_INCIDENT.md (Proposal 1 = §13e,
Proposal 2 = §13g).

Synthetic, production-shaped data only. Refuses any non-loopback host.
Creates and drops one scratch database per test case. Never touches
production. The repair/rollback scripts are extracted verbatim from the
document (markers `-- SCRIPT: P1-REPAIR` etc.), so the doc text is exactly
what gets executed.

Usage (from repo root):
    ./venv/Scripts/python backend/validate_quota_repair_sql.py
Env overrides: TEACHFLOW_QUOTA_CHECK_{HOST,PORT,USER,PASSWORD,DBNAME}
"""

from __future__ import annotations

import json
import os
import re
import sys
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

# Synthetic non-incident users; prefixes mirror the masked §13f evidence
# (full values are synthetic 36-char pads — production UUIDs were masked).
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

FINGERPRINT_SQL = """
SELECT md5(json_build_object(
  'units', (SELECT count(*) FROM usage_units),
  'units_md5', (SELECT md5(coalesce(string_agg(id || '|' || unit_key, ',' ORDER BY id), '')) FROM usage_units),
  'periods', (SELECT count(*) FROM usage_periods),
  'counter_sum', (SELECT coalesce(sum(units_used), 0) FROM usage_periods),
  'periods_md5', (SELECT md5(coalesce(string_agg(id || ':' || units_used, ',' ORDER BY id), '')) FROM usage_periods),
  'lessons', (SELECT count(*) FROM lesson_plans),
  'jobs', (SELECT count(*) FROM generation_jobs)
)::text)
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


def seed_sql() -> str:
    """Deterministic production-shaped synthetic seed; all counters are 0."""
    stmts: list[str] = []
    unit_n = 0

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
        stmts.append(
            "INSERT INTO usage_periods (id, user_id, period_type, period_key,"
            f" units_used, updated_at) VALUES ('{pid}', '{user}',"
            f" 'calendar_month', '{key}', 0, '2026-10-10 12:00:00');"
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

    # incident account: 6 matched units + 1 orphan, counter row 0, 10 jobs.
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

    # non-incident accounts: 14 period rows, 159 units, 1 orphan.
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
    return "\n".join(stmts)


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
    """Extract the fenced sql block whose first marker comment matches.

    Line-based fence walk: an opening fence is a line that strips to
    '```sql'; the next line that strips to '```' closes it. (A regex over
    the whole document is unsafe here: a '```sql' opener line can be
    consumed as a previous block's closer.)
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
    """Repair scripts must only mutate usage_units / usage_periods."""
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
            # key may contain spaces (MID-TERM code); created_at is last.
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
        self.seed = seed_sql()
        assert len(MID_TERM_CODE) == 30, "MID-TERM code must be 30 chars"
        assert len(scheme_of(U_MID)) + 1 + len(MID_TERM_CODE) == 67

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


def run_all() -> int:
    doc_text = DOC_PATH.read_text(encoding="utf-8")
    r = Runner(doc_text)
    results: list[tuple[str, bool, str]] = []
    dbname = "quota_rep_check"

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

    def case1(db: str) -> None:
        conn = r.seed_fresh(db)
        fp0 = r.fingerprint(conn)
        notices, err = r.run_script(conn, "P1-REPAIR")
        expect(err is None, f"P1-REPAIR failed: {err}")
        packet = parse_deleted(notices, p2=False)
        expect(packet["key"] == INC_ORPHAN_KEY, f"wrong key {packet['key']}")
        expect(r.one(conn, "SELECT count(*) FROM usage_units")[0] == 165,
               "expected 165 total units after P1")
        expect(r.one(conn, f"SELECT count(*) FROM usage_units WHERE user_id='{INC}'")[0] == 6,
               "incident units != 6")
        expect(r.one(conn, f"SELECT units_used FROM usage_periods WHERE user_id='{INC}'")[0] == 6,
               "incident counter != 6")
        expect(r.one(conn, f"SELECT count(*) FROM usage_units WHERE unit_key='{INC_ORPHAN_KEY}'")[0] == 0,
               "orphan still present")
        expect(r.fingerprint(conn) != fp0, "fingerprint unchanged after P1")
        conn.close()

    def case2(db: str) -> None:
        conn = r.seed_fresh(db)
        notices, err = r.run_script(conn, "P2-REPAIR")
        expect(err is None, f"P2-REPAIR failed: {err}")
        packet = parse_deleted(notices, p2=True)
        expect(packet["created_at"].startswith("2026-09-26 15:30:23"),
               f"unexpected created_at {packet['created_at']}")
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
        unmatched = r.one(conn, (
            f"SELECT count(*) FROM usage_units u WHERE u.user_id <> '{INC}'"
            " AND NOT EXISTS (SELECT 1 FROM lesson_plans l"
            "  WHERE l.owner_id = u.user_id AND l.scheme_id = u.scheme_id"
            "  AND jsonb_exists(l.indicator_codes::jsonb, split_part(u.unit_key, ':', 2)))"
        ))[0]
        expect(unmatched == 0, f"{unmatched} unmatched non-incident units remain")
        inc = r.one(conn, (
            f"SELECT (SELECT count(*) FROM usage_units WHERE user_id='{INC}'),"
            f" (SELECT units_used FROM usage_periods WHERE user_id='{INC}')"
        ))
        expect(tuple(inc) == (7, 0), f"incident account changed: {tuple(inc)}")
        conn.close()

    def case3(db: str) -> None:
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
        # (total units, sum of ALL counters = 6 incident + 158 non-incident,
        #  incident counter)
        expect(finals[0] == finals[1] == (164, 164, 6), f"orders diverged: {finals}")

    def case4(db: str) -> None:
        conn = r.seed_fresh(db)
        r.exec(conn, f"UPDATE usage_periods SET units_used=1 WHERE user_id='{INC}'")
        fp = r.fingerprint(conn)
        _, err = r.run_script(conn, "P1-REPAIR")
        expect_sqlstate(err, "TP001")
        expect(r.fingerprint(conn) == fp, "DB changed after refused P1 run")
        conn.close()
        conn = r.seed_fresh(db)
        r.exec(conn, f"UPDATE usage_periods SET units_used=1 WHERE user_id='{U_42}'")
        fp = r.fingerprint(conn)
        _, err = r.run_script(conn, "P2-REPAIR")
        expect_sqlstate(err, "TP001")
        expect(r.fingerprint(conn) == fp, "DB changed after refused P2 run")
        conn.close()

    def case5(db: str) -> None:
        conn = r.seed_fresh(db)
        r.exec(conn, f"DELETE FROM usage_units WHERE unit_key='{INC_ORPHAN_KEY}'")
        fp = r.fingerprint(conn)
        _, err = r.run_script(conn, "P1-REPAIR")
        expect_sqlstate(err, "TP001")
        expect(r.fingerprint(conn) == fp, "DB changed after refused P1 run")
        conn.close()
        conn = r.seed_fresh(db)
        r.exec(conn, "DELETE FROM usage_units"
                     f" WHERE created_at='{MID_ORPHAN_CREATED}'")
        fp = r.fingerprint(conn)
        _, err = r.run_script(conn, "P2-REPAIR")
        expect_sqlstate(err, "TP001")
        expect(r.fingerprint(conn) == fp, "DB changed after refused P2 run")
        conn.close()

    def case6(db: str) -> None:
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
        expect(r.fingerprint(conn) == fp, "DB changed after refused P1 run")
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
        expect(r.fingerprint(conn) == fp, "DB changed after refused P2 run")
        conn.close()

    def case7(db: str) -> None:
        conn = r.seed_fresh(db)
        r.exec(conn, (
            "UPDATE usage_units SET created_at='2026-10-09 00:21:17.000000'"
            f" WHERE unit_key='{INC_ORPHAN_KEY}'"
        ))
        fp = r.fingerprint(conn)
        _, err = r.run_script(conn, "P1-REPAIR")
        expect_sqlstate(err, "TP001")
        expect(r.fingerprint(conn) == fp, "DB changed after refused P1 run")
        conn.close()
        conn = r.seed_fresh(db)
        r.exec(conn, (
            "UPDATE usage_units SET unit_key = unit_key || 'X'"
            f" WHERE created_at='{MID_ORPHAN_CREATED}'"
        ))
        fp = r.fingerprint(conn)
        _, err = r.run_script(conn, "P2-REPAIR")
        expect_sqlstate(err, "TP001")
        expect(r.fingerprint(conn) == fp, "DB changed after refused P2 run")
        conn.close()

    def case8(db: str) -> None:
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

    def case9(db: str) -> None:
        conn = r.seed_fresh(db)
        fp0 = r.fingerprint(conn)
        notices, err = r.run_script(conn, "P1-REPAIR")
        expect(err is None, f"P1-REPAIR failed: {err}")
        packet = parse_deleted(notices, p2=False)
        rb = substitute(r.scripts["P1-ROLLBACK"], {
            "ORPHAN_ID": packet["id"],
            "ORPHAN_CREATED_AT": packet["created_at"],
            "REPAIRED_TS": parse_ts(notices),
        })
        _, err = r.run_script(conn, "P1-ROLLBACK", sql=rb)
        expect(err is None, f"P1-ROLLBACK failed: {err}")
        expect(r.fingerprint(conn) == fp0, "P1 rollback did not restore seed state")
        conn.close()
        conn = r.seed_fresh(db)
        fp0 = r.fingerprint(conn)
        notices, err = r.run_script(conn, "P2-REPAIR")
        expect(err is None, f"P2-REPAIR failed: {err}")
        packet = parse_deleted(notices, p2=True)
        rb = substitute(r.scripts["P2-ROLLBACK"], {
            "ORPHAN_ID": packet["id"],
            "ORPHAN_USER_ID": packet["user"],
            "ORPHAN_SCHEME_ID": packet["scheme"],
            "ORPHAN_UNIT_KEY": packet["key"],
            "ORPHAN_CREATED_AT": packet["created_at"],
            "REPAIRED_TS": parse_ts(notices),
        })
        _, err = r.run_script(conn, "P2-ROLLBACK", sql=rb)
        expect(err is None, f"P2-ROLLBACK failed: {err}")
        expect(r.fingerprint(conn) == fp0, "P2 rollback did not restore seed state")
        conn.close()

    def case10(db: str) -> None:
        conn = r.seed_fresh(db)
        notices, err = r.run_script(conn, "P1-REPAIR")
        expect(err is None, f"P1-REPAIR failed: {err}")
        packet = parse_deleted(notices, p2=False)
        ts = parse_ts(notices)
        r.exec(conn, (
            "INSERT INTO usage_units (id, user_id, period_type, period_key,"
            " unit_kind, unit_key, scheme_id, created_at) VALUES"
            f" ('act1','{INC}','calendar_month','2026-10','lesson_plan',"
            f" '{INC_SCHEME}:NEW-ACT','{INC_SCHEME}', now())"
        ))
        r.exec(conn, f"UPDATE usage_periods SET units_used=7 WHERE user_id='{INC}'")
        fp = r.fingerprint(conn)
        rb = substitute(r.scripts["P1-ROLLBACK"], {
            "ORPHAN_ID": packet["id"],
            "ORPHAN_CREATED_AT": packet["created_at"],
            "REPAIRED_TS": ts,
        })
        _, err = r.run_script(conn, "P1-ROLLBACK", sql=rb)
        expect_sqlstate(err, "TP003")
        expect(r.fingerprint(conn) == fp, "refused P1 rollback modified the DB")
        conn.close()

        conn = r.seed_fresh(db)
        notices, err = r.run_script(conn, "P2-REPAIR")
        expect(err is None, f"P2-REPAIR failed: {err}")
        packet = parse_deleted(notices, p2=True)
        ts = parse_ts(notices)
        r.exec(conn, f"UPDATE usage_periods SET units_used=6 WHERE user_id='{U_O34}'")
        fp = r.fingerprint(conn)
        rb = substitute(r.scripts["P2-ROLLBACK"], {
            "ORPHAN_ID": packet["id"], "ORPHAN_USER_ID": packet["user"],
            "ORPHAN_SCHEME_ID": packet["scheme"], "ORPHAN_UNIT_KEY": packet["key"],
            "ORPHAN_CREATED_AT": packet["created_at"], "REPAIRED_TS": ts,
        })
        _, err = r.run_script(conn, "P2-ROLLBACK", sql=rb)
        expect_sqlstate(err, "TP003")
        expect(r.fingerprint(conn) == fp, "refused P2 rollback (drift) modified the DB")
        conn.close()

        conn = r.seed_fresh(db)
        notices, err = r.run_script(conn, "P2-REPAIR")
        expect(err is None, f"P2-REPAIR failed: {err}")
        packet = parse_deleted(notices, p2=True)
        ts = parse_ts(notices)
        r.exec(conn, (
            "UPDATE usage_periods SET updated_at = updated_at + interval '1 second'"
            f" WHERE user_id='{U_O5A}'"
        ))
        fp = r.fingerprint(conn)
        rb = substitute(r.scripts["P2-ROLLBACK"], {
            "ORPHAN_ID": packet["id"], "ORPHAN_USER_ID": packet["user"],
            "ORPHAN_SCHEME_ID": packet["scheme"], "ORPHAN_UNIT_KEY": packet["key"],
            "ORPHAN_CREATED_AT": packet["created_at"], "REPAIRED_TS": ts,
        })
        _, err = r.run_script(conn, "P2-ROLLBACK", sql=rb)
        expect_sqlstate(err, "TP003")
        expect(r.fingerprint(conn) == fp, "refused P2 rollback (ts drift) modified the DB")
        conn.close()

    case("1  P1 valid commit", case1)
    case("2  P2 valid commit", case2)
    case("3  both orders converge", case3)
    case("4  wrong starting counter refuses", case4)
    case("5  missing orphan refuses", case5)
    case("6  extra orphan refuses", case6)
    case("7  changed orphan identity refuses", case7)
    case("8  tampered script aborts, no partial commit", case8)
    case("9  rollback restores faithfully", case9)
    case("10 rollback refuses after activity/drift", case10)

    width = max(len(name) for name, _, _ in results)
    print(f"Doc: {DOC_PATH}")
    print(f"Host: {r.host}:{r.port}  user={r.user}  (scratch DB per case, dropped after)")
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
