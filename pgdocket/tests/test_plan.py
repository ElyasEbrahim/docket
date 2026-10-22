"""Review planning (#20): the column's error after review stays ≤ ε with 95 % confidence."""
import math

import numpy as np

from pgdocket import plan


def _population(rng, N=3000):
    conf = np.round(rng.uniform(0.34, 1.0, N), 2)                      # Jev-like 0.01 grid
    wrong = (rng.random(N) > 0.2 + 0.8 * conf ** 2).astype(float)      # less sure → more often wrong
    return conf, wrong


def test_the_column_error_stays_within_epsilon_95_percent_of_the_time():
    rng = np.random.default_rng(31)
    for eps, n in ((0.05, 200), (0.03, 300), (0.10, 100)):
        trials, fails, reviewed = 400, 0, []
        for _ in range(trials):
            conf, wrong = _population(rng)
            lab = rng.choice(len(conf), n, replace=False)
            s = plan.cut(conf, conf[lab], wrong[lab], eps)
            assert s is not None
            fails += (wrong * (conf >= s)).mean() > eps
            reviewed.append((conf < s).mean())
        assert fails / trials <= 0.07, (eps, n, fails / trials)
        assert np.mean(reviewed) < 1                                     # it does leave rows to the AI


def test_too_few_labels_cannot_prove_epsilon():
    assert plan.labels_needed(0.05) == 59 and plan.labels_needed(0.01) == 299
    conf = np.linspace(0.5, 1, 100)
    assert plan.cut(conf, np.ones(58), np.zeros(58), 0.05) is None
    assert plan.cut(conf, np.ones(59), np.zeros(59), 0.05) is not None


def test_cut_keeps_the_most_confident_rows_and_reviews_the_rest():
    conf = np.array([0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0] * 100)
    wrong = (conf <= 0.5).astype(float)                                  # only the two least confident levels are wrong
    s = plan.cut(conf, conf, wrong, 0.02)
    assert s == 0.6 and math.isclose((conf < s).mean(), 2 / 7)
    p = plan.plan(conf, conf, wrong, 0.02)
    row = next(t for t in p["targets"] if t["requested"])
    assert row["review"] == 200 and row["cut"] == 0.6 and not row["review_all"]
    assert p["ai_error"] == 2 / 7
