import numpy as np
import pytest

from pgdocket.metrics import clopper_pearson_lower, precision_threshold


def test_clopper_pearson_solves_its_definition():
    # The one-sided lower bound L satisfies P(X >= k | n, L) = alpha; check with exact integer arithmetic.
    from math import comb

    def tail(k, n, p):
        return sum(comb(n, j) * p ** j * (1 - p) ** (n - j) for j in range(k, n + 1))

    assert clopper_pearson_lower(0, 10) == 0.0
    assert clopper_pearson_lower(10, 10) == pytest.approx(0.05 ** (1 / 10), abs=1e-9)
    for k, n in [(50, 100), (95, 100), (7, 30), (290, 300)]:
        assert tail(k, n, clopper_pearson_lower(k, n)) == pytest.approx(0.05, abs=1e-6)


def test_clopper_pearson_coverage():
    rng = np.random.default_rng(0)
    p, n, misses = 0.85, 60, 0
    for _ in range(2000):
        k = rng.binomial(n, p)
        misses += clopper_pearson_lower(k, n) > p
    assert misses / 2000 <= 0.06                 # nominal 5 %, conservative


def test_precision_threshold_holds_its_guarantee():
    rng = np.random.default_rng(1)
    fails, chosen = 0, 0
    for _ in range(300):
        score = rng.uniform(0, 1, 800)
        correct = rng.uniform(0, 1, 800) < score            # calibrated: precision rises with the threshold
        res = precision_threshold(score, correct, target=0.85)
        if res["chosen"]:
            chosen += 1
            t = res["chosen"]["threshold"]
            true_precision = (1 + t) / 2                     # E[score | score >= t] for uniform scores
            fails += true_precision < 0.85
    assert chosen > 250
    assert fails / 300 <= 0.05


def test_precision_threshold_refuses_when_target_is_unreachable():
    rng = np.random.default_rng(2)
    score = rng.uniform(0, 1, 500)
    correct = rng.uniform(0, 1, 500) < 0.5                   # scores carry no information
    assert precision_threshold(score, correct, target=0.9)["chosen"] is None


def test_precision_threshold_starts_where_the_target_is_provable():
    # 500 rows, top 30 % perfectly right: a start at 25 rows could never certify 90 %, which used to end the search.
    rng = np.random.default_rng(5)
    score = rng.uniform(0, 1, 500)
    correct = np.where(score > 0.7, True, rng.uniform(0, 1, 500) < 0.5)
    res = precision_threshold(score, correct, target=0.9)
    assert res["min_accept"] >= 58
    assert res["chosen"] and res["chosen"]["coverage"] >= 0.2


def test_the_threshold_holds_where_the_view_applies_it():
    """End to end: fit on a random sample of labels, mark `auto` on every row as the view does, and measure the true
    precision of the auto rows."""
    from pgdocket import calibration
    opts = ["a", "b", "c"]
    spec = {"kind": "choice", "question": "q", "options": [{"name": o} for o in opts]}
    rng = np.random.default_rng(12)
    trials, misses, found = 200, 0, 0
    for _ in range(trials):
        s = np.round(rng.uniform(0.34, 1.0, 2000), 2)                   # Jev-like 0.01 grid, with exact 1.0s
        pick = rng.integers(0, 3, 2000)
        right = rng.random(2000) < 0.25 + 0.75 * s                      # precision crosses 85 % mid-range
        truth = np.where(right, pick, (pick + rng.integers(1, 3, 2000)) % 3)
        answers = [{"choice": opts[p], "probabilities": {o: (x if i == p else (1 - x) / 2) for i, o in enumerate(opts)}}
                   for p, x in zip(pick, s)]
        lab = rng.choice(2000, 200, replace=False)
        cal = calibration.fit(spec, [answers[i] for i in lab], [opts[truth[i]] for i in lab], precision_target=0.85)
        # the view accepts exactly the labelled rows the threshold was tested on (it once applied another scale)
        assert np.mean([calibration.auto(answers[i], spec, cal) for i in lab]) == pytest.approx(cal["coverage"])
        if cal["threshold"] is None:
            continue
        found += 1
        auto = np.array([calibration.auto(a, spec, cal) for a in answers])
        misses += (pick[auto] == truth[auto]).mean() < 0.85
    assert found > trials / 2
    assert misses / found <= 0.07                                       # stated: at most 5 %
