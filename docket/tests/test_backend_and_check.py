import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import numpy as np
import pytest

from docket.backend import Backend, BackendError
from docket.check import CheckConfig, analyse_choice, analyse_noul, render


class FakeSystemOne(BaseHTTPRequestHandler):
    """Answers choice questions with the option named in the row's `want` field; fails the first request with 429."""
    protocol_version = "HTTP/1.1"
    requests = []
    fail_first = True

    def log_message(self, *a):
        pass

    def do_POST(self):
        req = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        cls = type(self)
        if cls.fail_first:
            cls.fail_first = False
            return self._send(429, {"error": "slow down"}, {"Retry-After": "0"})
        cls.requests.append(req)
        rows = req["state"]["rows"]
        answers = {}
        for qid, q in req["questions"].items():
            row = rows[int(qid[1:])]
            if q["type"] == "choice":
                opts = list(q["criteria"])
                want = next(o for o in opts if o.startswith(row["want"]))
                answers[qid] = {"type": "choice", "choice": want,
                                "probabilities": {o: (0.9 if o == want else 0.1 / (len(opts) - 1)) for o in opts}}
            else:
                answers[qid] = {"type": "noul", "noul": 0.8 if row["want"] == "yes" else 0.2}
        self._send(200, {"answers": answers, "usage": {"input_tokens": 100 * len(rows)}})

    def _send(self, code, obj, headers=None):
        data = json.dumps(obj).encode()
        self.send_response(code)
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


@pytest.fixture()
def server():
    FakeSystemOne.requests, FakeSystemOne.fail_first = [], True
    srv = ThreadingHTTPServer(("127.0.0.1", 0), FakeSystemOne)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_address[1]}/v1/systemone"
    srv.shutdown()


def test_backend_batches_keeps_order_and_retries(server):
    b = Backend(server, model="fake", concurrency=4)
    rows = [{"text": f"row {i}", "want": ["a", "b", "c"][i % 3]} for i in range(45)]
    answers = b.judge(rows, "choice", "which letter?", ["a: first", "b: second", "c: third"], batch_size=20)
    assert [a["choice"][0] for a in answers] == [r["want"] for r in rows]
    assert sorted(len(r["state"]["rows"]) for r in FakeSystemOne.requests) == [5, 20, 20]
    assert b.stats["requests"] == 3 and b.stats["input_tokens"] == 4500 and b.stats["retries"] == 1
    first = FakeSystemOne.requests[0]["questions"]["r0"]
    assert first["instructions"].startswith("For the record `rows[0]`") and "a: first" in first["criteria"]


def test_backend_requires_key_for_typesafe():
    with pytest.raises(BackendError):
        Backend("jev", api_key=None)


def _cfg(kind, **kw):
    base = dict(dsn="", table="demo.t", key="id", text=["body"], kind=kind, question="q?", label_column="label",
                precision_target=0.8)
    base.update(kw)
    return CheckConfig(**base)


def test_choice_analysis_and_report():
    rng = np.random.default_rng(3)
    cfg = _cfg("choice", options=[{"name": n, "description": d} for n, d in [("a", "first"), ("b", "second"), ("c", "third")]])
    display = ["a: first", "b: second", "c: third"]
    sample, answers = [], []
    for i in range(400):
        label = "abc"[i % 3]
        right = rng.random() < 0.8
        pick = label if right else "abc"[(i + 1) % 3]
        probs = {d: (0.85 if d[0] == pick else 0.075) for d in display}     # over-confident: 85 % vs 80 % right
        sample.append({"key": str(i), "record": {"body": "SECRET-ROW-TEXT"}, "label": label})
        answers.append({"type": "choice", "choice": display["abc".index(pick)], "probabilities": probs})
    a = analyse_choice(cfg, sample, answers)
    assert 0.75 < a["accuracy"] < 0.85
    assert a["threshold"]["tested"]
    a.pop("_top")
    result = {"config": {**cfg.__dict__}, "analysis": a, "stability": {"rows": 50, "changed": 0.04},
              "batching": {"rows": 50, "changed": 0.12, "accuracy_single": 0.8, "accuracy_batched": 0.74},
              "backend": {"url": "fake", "model": "m", "batch_size": 1}, "created_at": "now", "docket_version": "0",
              "sample": {"labeled_rows": 400, "rows_in_scope": 1000, "table_rows": 2000, "label_counts": {}},
              "cost": {"requests": 400, "input_tokens": 40000, "usd": 0.0017, "tokens_per_row": 100,
                       "projected_usd_table": 0.0084, "projected_usd_per_million_rows": 4.2, "seconds": 3}}
    md = render(result)
    assert "Judge one row per request" in md and "Store answers" in md
    assert "SECRET-ROW-TEXT" not in md                   # the report never contains row text


def test_noul_analysis_threshold_has_recall():
    rng = np.random.default_rng(4)
    cfg = _cfg("noul", positive="yes")
    sample, answers = [], []
    for i in range(500):
        yes = rng.random() < 0.3
        p = float(np.clip(rng.normal(0.75 if yes else 0.3, 0.15), 0.01, 0.99))
        sample.append({"key": str(i), "record": {"body": "x"}, "label": "yes" if yes else "no"})
        answers.append({"type": "noul", "noul": p})
    a = analyse_noul(cfg, sample, answers)
    assert a["auroc"] > 0.9
    assert a["threshold"]["chosen"] and 0 < a["threshold"]["chosen"]["recall"] <= 1
