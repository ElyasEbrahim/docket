import numpy as np
import pytest

from docket.metrics import clopper_pearson_lower, precision_threshold


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
