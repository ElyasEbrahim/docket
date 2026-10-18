"""A simulated Jev-compatible backend (`POST /v1/systemone`) with known flaws, used to validate the harness.

It reads ground truth for each narrative from bench.complaints. Its probabilities are **exactly calibrated by
construction**: it draws a noisy signal from the label, then reports the Bayes posterior given that signal and
the sample's class priors. Flaws are then applied as known distortions:

  choice:  z_j = SIGNAL·[j = truth] + ε_j,  ε_j ~ N(0, NOISE²)  (ε keyed by option text, so it moves with the option)
           calibrated logit_j = SIGNAL·z_j / NOISE² + log π_j
           reported = softmax((logit_j + FIRST_BIAS·[j listed first]) / TEMPERATURE)
  noul:    x ~ N(±SIGNAL/2, NOISE²)
           calibrated logit = logit(prevalence) + SIGNAL·x / NOISE²
           reported = sigmoid(logit / TEMPERATURE)

With TEMPERATURE = 1 and FIRST_BIAS = 0 the backend is calibrated. TEMPERATURE < 1 makes it over-confident: a
correct harness then fits a temperature ≈ 1 / TEMPERATURE. FIRST_BIAS > 0 adds a first-option lean (Jev
documents one). Every answer is deterministic given SIM_SEED.

Never use this for anything except testing the harness: its answers are derived from the labels.
"""
import argparse
import hashlib
import json
import math
import os
import random
import threading
import time
from collections import Counter
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .tasks import Truth, default_experiments, noul_family_for_condition, noul_truth


class Knobs:
    def __init__(self, signal=2.5, noise=1.0, temperature=0.5, first_bias=0.6, seed=7):
        self.signal, self.noise, self.temperature = signal, noise, temperature
        self.first_bias, self.seed = first_bias, seed

    @classmethod
    def from_env(cls):
        e = os.environ
        return cls(float(e.get("SIM_SIGNAL", 2.5)), float(e.get("SIM_NOISE", 1.0)),
                   float(e.get("SIM_TEMPERATURE", 0.5)), float(e.get("SIM_FIRST_BIAS", 0.6)),
                   int(e.get("SIM_SEED", 7)))

    def as_dict(self):
        return dict(signal=self.signal, noise=self.noise, temperature=self.temperature,
                    first_bias=self.first_bias, seed=self.seed)


def _rng(*parts):
    h = hashlib.sha256("\x1f".join(str(p) for p in parts).encode()).digest()
    return random.Random(int.from_bytes(h[:8], "big"))


def _softmax(z):
    m = max(z)
    e = [math.exp(v - m) for v in z]
    s = sum(e)
    return [v / s for v in e]


def _sigmoid(x):
    return 1.0 / (1.0 + math.exp(-x)) if x >= 0 else math.exp(x) / (1.0 + math.exp(x))


class Truths:
    """text_hash → Truth plus the sample statistics the calibrated posterior needs (class priors, prevalences)."""

    def __init__(self, data):
        self.data = data
        counts = Counter(t.product for t in data.values())
        n = max(sum(counts.values()), 1)
        self.priors = {p: c / n for p, c in counts.items()}
        self.floor = min(self.priors.values()) / 2 if self.priors else 0.01   # prior for options nobody has
        self.prevalence = {}
        for e in default_experiments():
            if e.kind == "noul":
                k = sum(noul_truth(e.family, t) for t in data.values())
                self.prevalence[e.family] = min(max(k / n, 0.01), 0.99)

    def get(self, text_hash):
        return self.data.get(text_hash)


def answer_choice(knobs, text_hash, truth, options, truths):
    logits = []
    for pos, opt in enumerate(options):
        z = _rng(knobs.seed, "noise", text_hash, opt).gauss(0.0, knobs.noise)
        if truth is not None and opt == truth.product:
            z += knobs.signal
        calibrated = knobs.signal * z / knobs.noise ** 2 + math.log(truths.priors.get(opt, truths.floor))
        logits.append((calibrated + (knobs.first_bias if pos == 0 else 0.0)) / knobs.temperature)
    p = _softmax(logits)
    best = max(range(len(options)), key=lambda i: p[i])
    return {"type": "choice", "choice": options[best],
            "probabilities": {o: round(pi, 6) for o, pi in zip(options, p)},
            "confidence": round(p[best], 6)}


def answer_noul(knobs, text_hash, truth, condition, truths):
    family = noul_family_for_condition(condition)
    if truth is None or family is None:
        return {"type": "noul", "noul": round(_rng(knobs.seed, "unknown", text_hash, condition).random(), 6)}
    y = noul_truth(family, truth)
    x = _rng(knobs.seed, "noise", text_hash, condition).gauss(knobs.signal / 2 * (1 if y else -1), knobs.noise)
    prev = truths.prevalence[family]
    calibrated = math.log(prev / (1 - prev)) + knobs.signal * x / knobs.noise ** 2
    return {"type": "noul", "noul": round(_sigmoid(calibrated / knobs.temperature), 6)}


def answer_score(levels):
    n = len(levels)
    return {"type": "score", "score": (n - 1) / 2, "legend": {str(i): l for i, l in enumerate(levels)},
            "probabilities": {str(i): 1.0 / n for i in range(n)}, "confidence": 1.0 / n}


class TruthStore:
    """Truths loaded from bench.complaints, reloaded (rate-limited) when an unknown narrative arrives."""

    def __init__(self, loader):
        self.loader, self.current, self.loaded_at, self.lock = loader, Truths({}), 0.0, threading.Lock()

    def snapshot(self, hashes):
        if any(h not in self.current.data for h in hashes) and time.time() - self.loaded_at > 5:
            with self.lock:
                if time.time() - self.loaded_at > 5:
                    self.current, self.loaded_at = Truths(self.loader()), time.time()
        return self.current


def db_loader():
    from .db import connect
    try:
        with connect() as conn, conn.cursor() as cur:
            cur.execute("SELECT text_hash, product, issue FROM bench.complaints")
            return {h: Truth(p, i or "") for h, p, i in cur.fetchall()}
    except Exception as e:  # table not created yet
        print(f"sim: could not load truth ({type(e).__name__}: {e})", flush=True)
        return {}


def handle_request(knobs, truths, req):
    """truths: a Truths object (tests) or a TruthStore (server)."""
    state, questions = req.get("state", {}), req.get("questions", {})
    rows = state.get("rows", [])
    texts = []
    for qid in questions:
        i = int(qid[1:])
        row = rows[i] if i < len(rows) else {}
        texts.append((qid, row.get("narrative", "") if isinstance(row, dict) else str(row)))
    hashes = {qid: hashlib.md5(t.encode("utf-8")).hexdigest() for qid, t in texts}
    snap = truths.snapshot(hashes.values()) if isinstance(truths, TruthStore) else truths
    log = os.environ.get("SIM_LOG")
    if log:   # one line per request: the narratives' hashes in batch order (checks pg-jev's batching)
        with open(log, "a") as f:
            f.write(json.dumps([hashes[qid] for qid in sorted(hashes, key=lambda q: int(q[1:]))]) + "\n")
    answers = {}
    for qid, q in questions.items():
        h = hashes[qid]
        truth = snap.get(h)
        if q["type"] == "choice":
            answers[qid] = answer_choice(knobs, h, truth, list(q["criteria"].keys()), snap)
        elif q["type"] == "noul":
            answers[qid] = answer_noul(knobs, h, truth, state.get("condition", ""), snap)
        elif q["type"] == "score":
            answers[qid] = answer_score(list(q["criteria"]))
        else:
            raise ValueError("unknown question type %r" % q["type"])
    return answers


def make_handler(knobs, truths):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *a):
            pass

        def do_GET(self):
            self._send(200, {"ok": True, "knobs": knobs.as_dict(), "truths": len(truths.current.data)})

        def do_POST(self):
            body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
            try:
                answers = handle_request(knobs, truths, json.loads(body))
            except (ValueError, KeyError) as e:
                return self._send(422, {"error": str(e)})
            self._send(200, {"model": "jev-sim", "answers": answers,
                             "usage": {"input_tokens": len(body) // 4, "output_tokens": 0}})

        def _send(self, code, obj):
            data = json.dumps(obj).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

    return Handler


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--port", type=int, default=8787)
    args = ap.parse_args()
    knobs = Knobs.from_env()
    truths = TruthStore(db_loader)
    print(f"jev-sim on 0.0.0.0:{args.port} knobs={knobs.as_dict()}", flush=True)
    ThreadingHTTPServer(("0.0.0.0", args.port), make_handler(knobs, truths)).serve_forever()


if __name__ == "__main__":
    main()
