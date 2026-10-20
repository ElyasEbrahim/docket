"""Ledger integration tests against a real Postgres (set TEST_DATABASE_URL to a superuser connection).

The superuser is only used to create a throwaway database and two roles. Everything pgdocket does runs as an
ordinary role (`owner`), and the application writes to its table as a second role (`app`) that has no grant
at all on the docket schema. This is the setup of a managed Postgres.
"""
import json
import os
import uuid

import pytest

psycopg = pytest.importorskip("psycopg")
from psycopg.conninfo import make_conninfo  # noqa: E402

from pgdocket import calibration, ledger  # noqa: E402
from pgdocket.tests.fakes import FakeSystemOne, serve  # noqa: E402
from pgdocket.worker import Worker  # noqa: E402

BASE = os.environ.get("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not BASE, reason="set TEST_DATABASE_URL to run ledger integration tests")


@pytest.fixture(scope="module")
def env():
    tag = uuid.uuid4().hex[:8]
    db, owner, app, pw = f"docket_it_{tag}", f"docket_owner_{tag}", f"docket_app_{tag}", "pw-" + tag
    with psycopg.connect(BASE, autocommit=True) as su:
        su.execute(f"CREATE ROLE {owner} LOGIN PASSWORD '{pw}' NOSUPERUSER NOCREATEDB NOCREATEROLE")
        su.execute(f"CREATE ROLE {app} LOGIN PASSWORD '{pw}' NOSUPERUSER")
        su.execute(f"CREATE DATABASE {db} OWNER {owner}")
    owner_dsn = make_conninfo(BASE, dbname=db, user=owner, password=pw)
    app_dsn = make_conninfo(BASE, dbname=db, user=app, password=pw)
    with psycopg.connect(owner_dsn, autocommit=True) as c:
        c.execute("CREATE SCHEMA shop")
        c.execute("CREATE TABLE shop.tickets (id int PRIMARY KEY, subject text, body text, priority int, team text)")
        c.execute(f"GRANT USAGE ON SCHEMA shop TO {app}")
        c.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON shop.tickets TO {app}")
    url, shutdown = serve()
    yield {"owner": owner_dsn, "app": app_dsn, "url": url}
    shutdown()
    with psycopg.connect(BASE, autocommit=True) as su:
        su.execute(f"DROP DATABASE IF EXISTS {db} WITH (FORCE)")
        su.execute(f"DROP ROLE IF EXISTS {owner}")
        su.execute(f"DROP ROLE IF EXISTS {app}")


OPTIONS = [{"name": "billing", "description": "invoices and refunds"}, {"name": "technical"}, {"name": "sales"}]


def _spec(url):
    return {"kind": "choice", "question": "Which team should handle this ticket?", "options": OPTIONS,
            "backend": url, "model": "fake", "batch_size": 1}


def _view(dsn):
    with psycopg.connect(dsn) as c:
        return {r[0]: r[1:] for r in c.execute("SELECT key, status, answer, confidence, version FROM docket.v_triage ORDER BY key")}


def test_install_is_idempotent_and_needs_no_superuser(env):
    with psycopg.connect(env["owner"]) as c:
        assert c.execute("SELECT rolsuper FROM pg_roles WHERE rolname = current_user").fetchone()[0] is False
    assert ledger.install(env["owner"]) == ["001", "002"]
    assert ledger.install(env["owner"]) == []


def test_create_backfills_and_app_inserts_enqueue_without_grants(env):
    with psycopg.connect(env["owner"], autocommit=True) as c:
        c.execute("INSERT INTO shop.tickets VALUES (1, 'refund', 'billing problem', 1, 'billing')")
    did, queued = ledger.create(env["owner"], "triage", "shop.tickets", "id", ["subject", "body"], _spec(env["url"]))
    assert queued == 1                                        # the existing row was backfilled
    with psycopg.connect(env["app"], autocommit=True) as c:   # the app role can't even see docket.*
        with pytest.raises(psycopg.errors.InsufficientPrivilege):
            c.execute("SELECT * FROM docket.queue")
    with psycopg.connect(env["app"], autocommit=True) as c:
        c.execute("INSERT INTO shop.tickets VALUES (2, 'crash', 'technical error', 2, 'technical'), "
                  "(3, 'quote', 'sales question', 3, 'sales')")
    v = _view(env["owner"])
    assert {k: s[0] for k, s in v.items()} == {1: "pending", 2: "pending", 3: "pending"}


def test_worker_judges_and_view_reads(env):
    totals = Worker(env["owner"], poll=0.1, log=lambda *a: None).run(once=True)
    assert totals["judged"] == 3
    v = _view(env["owner"])
    assert {k: (s[0], s[1]) for k, s in v.items()} == {1: ("judged", "billing"), 2: ("judged", "technical"),
                                                       3: ("judged", "sales")}
    assert all(abs(s[2] - 0.9) < 1e-9 for s in v.values())    # uncalibrated: the raw top probability
    with psycopg.connect(env["owner"]) as c:
        assert c.execute("SELECT count(*) FROM docket.queue").fetchone()[0] == 0
        assert c.execute("SELECT count(*) FROM docket.judgment").fetchone()[0] == 3


def test_only_changes_to_judged_columns_requeue(env):
    with psycopg.connect(env["app"], autocommit=True) as c:
        c.execute("UPDATE shop.tickets SET priority = 9 WHERE id = 1")             # not a judged column
        c.execute("UPDATE shop.tickets SET body = body WHERE id = 2")              # same value
        c.execute("UPDATE shop.tickets SET body = 'sales lead after all' WHERE id = 3")
    with psycopg.connect(env["owner"]) as c:
        assert [r[0] for r in c.execute("SELECT row_key FROM docket.queue")] == ["3"]
    Worker(env["owner"], poll=0.1, log=lambda *a: None).run(once=True)
    with psycopg.connect(env["owner"]) as c:
        assert c.execute("SELECT count(*) FROM docket.judgment WHERE row_key = '3'").fetchone()[0] == 2  # ledger keeps both


def test_unchanged_input_is_not_judged_again(env):
    with psycopg.connect(env["owner"], autocommit=True) as c:
        c.execute("SELECT docket.backfill('triage')")                           # re-queue every row
    totals = Worker(env["owner"], poll=0.1, log=lambda *a: None).run(once=True)
    assert totals["judged"] == 0 and totals["skipped_unchanged"] == 3


def test_deleted_rows_leave_the_view_but_stay_in_the_ledger(env):
    with psycopg.connect(env["app"], autocommit=True) as c:
        c.execute("INSERT INTO shop.tickets VALUES (4, 'bill', 'billing again', 1, 'billing')")
        c.execute("DELETE FROM shop.tickets WHERE id = 4")
    totals = Worker(env["owner"], poll=0.1, log=lambda *a: None).run(once=True)
    assert totals["deleted_rows"] == 1
    assert 4 not in _view(env["owner"])


def test_backend_errors_back_off_then_dead_letter(env):
    FakeSystemOne.fail_rows_containing = "POISON"
    try:
        with psycopg.connect(env["app"], autocommit=True) as c:
            c.execute("INSERT INTO shop.tickets VALUES (5, 'x', 'POISON', 1, 'billing')")
        w = Worker(env["owner"], poll=0.1, log=lambda *a: None)
        for _ in range(5):                                                       # skip the back-off waits
            with psycopg.connect(env["owner"], autocommit=True) as c:
                c.execute("UPDATE docket.queue SET locked_until = NULL WHERE row_key = '5'")
            w.process_once()
        assert _view(env["owner"])[5][0] == "error"
        with psycopg.connect(env["owner"]) as c:
            attempts, err = c.execute("SELECT attempts, last_error FROM docket.queue WHERE row_key = '5'").fetchone()
        assert attempts == 5 and "400" in err
    finally:
        FakeSystemOne.fail_rows_containing = None


def test_labels_calibration_and_sql_python_parity(env):
    teams = ["billing", "technical", "sales"]
    # The fake model answers the team named in the body; the label disagrees for every third row, so the model's
    # 0.9 confidence is too high (it's right about 2/3 of the time) and calibration must pull it down.
    rows = [(100 + i, f"t{i}", teams[i % 3], 1, teams[i % 3] if i % 3 else teams[(i + 1) % 3]) for i in range(90)]
    with psycopg.connect(env["app"], autocommit=True) as c:
        with c.cursor() as cur:
            cur.executemany("INSERT INTO shop.tickets VALUES (%s, %s, %s, %s, %s)", rows)
    Worker(env["owner"], poll=0.1, log=lambda *a: None).run(once=True)
    assert ledger.import_labels(env["owner"], "triage", column="team") >= 90
    cal = ledger.calibrate(env["owner"], "triage", precision_target=0.5)
    assert cal["method"] == "temperature" and cal["n_labels"] >= 90
    with psycopg.connect(env["owner"]) as c:
        spec, stored = c.execute("SELECT spec, calibration FROM docket.version WHERE version = 1").fetchone()
        pairs = c.execute("SELECT j.answer, docket.calibrated(j.answer, %s, %s) FROM docket.judgment j",
                          (json.dumps(spec), json.dumps(stored))).fetchall()
        view_conf = c.execute("SELECT count(*) FROM docket.v_triage WHERE confidence < 0.9").fetchone()[0]
    for answer, sql_value in pairs:
        assert sql_value == pytest.approx(calibration.calibrated(answer, spec, stored), rel=1e-9)
    assert view_conf > 0                                    # the over-confident 0.9s were pulled down


def test_status_view(env):
    s = {r["name"]: r for r in ledger.status(env["owner"])}["triage"]
    assert s["errors"] == 1 and s["labels"] >= 90 and s["calibrated"] and s["judged"] >= 93


def test_drop_decision_removes_triggers_view_and_ledger(env):
    with psycopg.connect(env["owner"], autocommit=True) as c:
        c.execute("SELECT docket.drop_decision('triage')")
        assert c.execute("SELECT to_regclass('docket.v_triage')").fetchone()[0] is None
        assert c.execute("SELECT count(*) FROM docket.judgment").fetchone()[0] == 0
    with psycopg.connect(env["app"], autocommit=True) as c:                 # inserts no longer enqueue
        c.execute("INSERT INTO shop.tickets VALUES (999, 'x', 'billing', 1, 'billing')")
    with psycopg.connect(env["owner"]) as c:
        assert c.execute("SELECT count(*) FROM docket.queue").fetchone()[0] == 0
        assert c.execute("SELECT count(*) FROM shop.tickets").fetchone()[0] > 90   # the source table is untouched


def _counts_setup(env):
    """400 orders; the fake model answers the team named in `body`, which disagrees with the human `team` for 1 in 4."""
    teams = ["billing", "technical", "sales"]
    with psycopg.connect(env["owner"], autocommit=True) as c:
        c.execute("CREATE TABLE shop.orders (id int PRIMARY KEY, body text, team text, urgent text)")
        rows = [(i, teams[i % 3] if i % 4 else teams[(i + 1) % 3], teams[i % 3], "yes" if i % 5 == 0 else "no")
                for i in range(1, 401)]
        with c.cursor() as cur:
            cur.executemany("INSERT INTO shop.orders VALUES (%s, %s, %s, %s)", rows)
    spec = dict(_spec(env["url"]))
    ledger.create(env["owner"], "counts", "shop.orders", "id", ["body"], spec)
    Worker(env["owner"], poll=0.1, log=lambda *a: None).run(once=True)


def test_estimate_matches_python_and_respects_sampling(env):
    from pgdocket.estimate import ppi_share
    _counts_setup(env)
    # whole-column labels are not a random sample: refused by default
    ledger.import_labels(env["owner"], "counts", column="team")
    rows = ledger.estimate(env["owner"], "counts")
    assert all(r["estimate"] is None and "no random-sample labels" in r["note"] for r in rows)
    assert all(r["estimate"] is not None for r in ledger.estimate(env["owner"], "counts", include_manual=True))
    # a random sample of 120
    with psycopg.connect(env["owner"], autocommit=True) as c:
        c.execute("DELETE FROM docket.label WHERE decision_id = (SELECT id FROM docket.decision WHERE name = 'counts')")
    assert ledger.import_labels(env["owner"], "counts", column="team", sample=120, seed="7") == 120
    rows = {r["answer"]: r for r in ledger.estimate(env["owner"], "counts")}
    with psycopg.connect(env["owner"]) as c:
        data = c.execute(
            "SELECT v.answer, t.team, l.label IS NOT NULL FROM docket.v_counts v JOIN shop.orders t ON t.id = v.key "
            "LEFT JOIN docket.label l ON l.decision_id = (SELECT id FROM docket.decision WHERE name = 'counts') "
            "AND l.row_key = v.key::text AND l.sampling = 'random'").fetchall()
    for answer in ["billing", "technical", "sales"]:
        f = [int(a == answer) for a, _, _ in data]
        y = [int(t == answer) for _, t, _ in data]
        lab = [x for _, _, x in data]
        py = ppi_share([fi for fi, l in zip(f, lab) if not l], [fi for fi, l in zip(f, lab) if l],
                       [yi for yi, l in zip(y, lab) if l])
        r = rows[answer]
        assert r["labels"] == 120 and r["judged"] == 400
        assert r["estimate"] == pytest.approx(py["estimate"] * 400, rel=1e-9)
        assert r["ci_low"] == pytest.approx(py["ci_low"] * 400, rel=1e-9)
        assert r["ci_high"] == pytest.approx(py["ci_high"] * 400, rel=1e-9)
        assert r["labels_only_low"] == pytest.approx(py["labels_low"] * 400, rel=1e-9)
        assert r["lambda"] == pytest.approx(py["lam"], rel=1e-9, abs=1e-12)
        assert r["reliable"] == py["reliable"]
        truth = sum(y)
        assert r["ci_low"] <= truth <= r["ci_high"]                      # this draw covers the truth


def test_estimate_scope_uses_only_labels_in_scope(env):
    rows = ledger.estimate(env["owner"], "counts", answer="billing", where="id <= 200")
    with psycopg.connect(env["owner"]) as c:
        n = c.execute("SELECT count(*) FROM docket.label l JOIN docket.decision d ON d.id = l.decision_id "
                      "WHERE d.name = 'counts' AND l.sampling = 'random' AND l.row_key::int <= 200").fetchone()[0]
    assert rows[0]["judged"] == 200 and rows[0]["labels"] == n


def test_yes_no_labels_are_normalised_and_estimated(env):
    spec = {"kind": "noul", "question": "the order is urgent", "backend": env["url"], "model": "fake", "batch_size": 1}
    ledger.create(env["owner"], "urgent", "shop.orders", "id", ["body"], spec)
    Worker(env["owner"], poll=0.1, log=lambda *a: None).run(once=True)
    with pytest.raises(SystemExit):
        ledger.import_labels(env["owner"], "urgent", column="urgent", sample=150)          # needs --positive
    ledger.import_labels(env["owner"], "urgent", column="urgent", sample=150, positive="yes")
    with psycopg.connect(env["owner"]) as c:
        assert {r[0] for r in c.execute("SELECT DISTINCT label FROM docket.label l JOIN docket.decision d "
                                        "ON d.id = l.decision_id WHERE d.name = 'urgent'")} == {"yes", "no"}
    r = ledger.estimate(env["owner"], "urgent")[0]
    assert r["answer"] == "yes" and r["labels"] == 150 and r["estimate"] is not None
