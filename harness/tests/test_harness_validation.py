"""End-to-end check that the analysis recovers flaws planted in the simulated backend (no database needed).

The sim is calibrated by construction when temperature = 1 and first_bias = 0, so:
  * calibrated config  → small ECE, fitted temperature ≈ 1, no first-position lift
  * distorted config   → larger ECE, fitted temperature ≈ 1 / sim temperature, positive lift, ECE drops after
                         recalibration
"""
import hashlib
import random

import pytest

from jevbench.report import analyse_choice, analyse_noul, analyse_order
from jevbench.sim import Knobs, Truths, handle_request
from jevbench.tasks import INCORRECT_REPORT_ISSUES, PRODUCT_OPTIONS, Truth, default_experiments

N = 3000
WEIGHTS = [50, 14, 7, 8, 6, 3, 3, 2, 2]


@pytest.fixture(scope="module")
def corpus():
    rng = random.Random(11)
    data = {}
    for i in range(N):
        product = rng.choices(PRODUCT_OPTIONS, WEIGHTS)[0]
        issue = next(iter(INCORRECT_REPORT_ISSUES)) if product == "credit reporting" and rng.random() < 0.4 else "x"
        text = f"synthetic complaint {i}"
        data[hashlib.md5(text.encode()).hexdigest()] = (text, Truth(product, issue))
    return data


def run_sim(knobs, corpus):
    truths = Truths({h: t for h, (_, t) in corpus.items()})
    items = list(corpus.items())
    answers, exps = {}, {}
    for e in default_experiments():
        exps[e.name] = {"name": e.name, "kind": e.kind, "question": e.question, "options": e.options_list,
                        "family": e.family}
        out = {}
        for start in range(0, len(items), 20):
            batch = items[start:start + 20]
            state = {"rows": [{"narrative": text} for _, (text, _) in batch]}
            if e.kind == "noul":
                state["condition"] = e.question
            questions = {f"r{i}": ({"type": "choice", "criteria": {o: None for o in e.options}}
                                   if e.kind == "choice" else {"type": "noul"}) for i in range(len(batch))}
            res = handle_request(knobs, truths, {"state": state, "questions": questions})
            for i, (h, _) in enumerate(batch):
                out[h] = res[f"r{i}"]
        answers[e.name] = out
    truth = {h: t for h, (_, t) in corpus.items()}
    per = {n: (analyse_choice(exps[n], answers[n], truth) if exps[n]["kind"] == "choice"
               else analyse_noul(exps[n], answers[n], truth)) for n in exps}
    return per, analyse_order(exps, per, truth)


def test_calibrated_backend_reads_as_calibrated(corpus):
    per, order = run_sim(Knobs(temperature=1.0, first_bias=0.0), corpus)
    base = per["choice_base"]
    assert base["ece"] < 0.035
    assert 0.8 < base["temperature"] < 1.25
    assert per["noul_debt_collection"]["ece"] < 0.04
    lo, hi = order["first_position_prob_lift_ci"]
    assert lo < 0.0 < hi or abs(order["first_position_prob_lift"]) < 0.005


def test_overconfident_biased_backend_is_caught(corpus):
    per, order = run_sim(Knobs(temperature=0.5, first_bias=0.6), corpus)
    base = per["choice_base"]
    assert base["ece"] > 0.05
    assert 1.6 < base["temperature"] < 2.6                # ≈ 1 / 0.5, blurred by the first-option bias
    assert base["ece_after_temperature"] < base["ece"] / 2
    assert order["first_position_prob_lift_ci"][0] > 0.0
    assert order["flip_rate"] > 0.0


def test_overconfident_noul_is_caught_when_signal_is_moderate(corpus):
    # With a strong signal most probabilities sit near 0 or 1 and ECE barely moves under over-confidence
    # (a property of ECE, not of the harness); a moderate signal makes the distortion visible.
    calibrated, _ = run_sim(Knobs(signal=1.5, temperature=1.0, first_bias=0.0), corpus)
    distorted, _ = run_sim(Knobs(signal=1.5, temperature=0.4, first_bias=0.0), corpus)
    assert calibrated["noul_debt_collection"]["ece"] < 0.04
    noul = distorted["noul_debt_collection"]
    assert noul["ece"] > 0.06
    assert noul["ece_after_isotonic"] < noul["ece"] / 2
    assert noul["nll"] > calibrated["noul_debt_collection"]["nll"]
