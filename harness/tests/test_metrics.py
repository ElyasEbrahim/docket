import numpy as np
import pytest

from jevbench import metrics as M


def test_ece_zero_when_perfectly_calibrated_bins():
    # Within each bin, accuracy equals confidence exactly.
    conf = np.array([0.25] * 4 + [0.75] * 4)
    correct = np.array([1, 0, 0, 0, 1, 1, 1, 0])
    assert M.ece(conf, correct, n_bins=10) == pytest.approx(0.0)


def test_ece_detects_overconfidence():
    conf = np.full(100, 0.9)
    correct = np.r_[np.ones(60), np.zeros(40)]
    assert M.ece(conf, correct, n_bins=10) == pytest.approx(0.3)


def test_ece_small_for_sampled_calibrated_probabilities():
    rng = np.random.default_rng(1)
    p = rng.uniform(0, 1, 20000)
    y = rng.uniform(0, 1, 20000) < p
    assert M.ece(p, y, 15) < 0.02


def test_auroc_known_values_and_ties():
    assert M.auroc([0.1, 0.2, 0.8, 0.9], [0, 0, 1, 1]) == pytest.approx(1.0)
    assert M.auroc([0.9, 0.8, 0.2, 0.1], [0, 0, 1, 1]) == pytest.approx(0.0)
    assert M.auroc([0.5, 0.5, 0.5, 0.5], [0, 1, 0, 1]) == pytest.approx(0.5)


def test_isotonic_is_monotone_and_fixes_distortion():
    rng = np.random.default_rng(2)
    true_p = rng.uniform(0, 1, 5000)
    y = (rng.uniform(0, 1, 5000) < true_p).astype(float)
    distorted = true_p ** 3                     # monotone distortion → badly calibrated
    assert M.ece(distorted, y, 15) > 0.15
    fixed = M.crossfit_binary(distorted, y, "isotonic")
    assert M.ece(fixed, y, 15) < 0.04
    knots = M.isotonic_fit(distorted, y)
    assert np.all(np.diff(knots[1]) >= -1e-12)


def test_platt_recovers_logistic_distortion():
    rng = np.random.default_rng(3)
    logit = rng.normal(0, 2, 8000)
    y = (rng.uniform(0, 1, 8000) < 1 / (1 + np.exp(-logit))).astype(float)
    overconfident = 1 / (1 + np.exp(-3 * logit))
    a, b = M.platt_fit(overconfident, y)
    assert a == pytest.approx(1 / 3, abs=0.05)
    assert abs(b) < 0.1


def test_temperature_recovers_known_temperature():
    rng = np.random.default_rng(4)
    n, k = 6000, 5
    logits = rng.normal(0, 2, (n, k))
    P_true = np.exp(logits) / np.exp(logits).sum(1, keepdims=True)
    y = np.array([rng.choice(k, p=p) for p in P_true])
    P_sharp = M.temperature_apply(P_true, 0.4)   # over-confident by T = 0.4
    T = M.temperature_fit(P_sharp, y)
    assert T == pytest.approx(1 / 0.4, rel=0.1)


def test_bootstrap_ci_covers_mean():
    x = np.random.default_rng(5).normal(1.0, 1.0, 2000)
    lo, hi = M.bootstrap_ci(np.mean, [x], n_boot=500)
    assert lo < 1.0 < hi
    assert hi - lo < 0.15


def test_macro_f1_and_prf():
    p, r, f = M.prf([1, 1, 0, 0], [1, 0, 1, 0])
    assert (p, r, f) == (0.5, 0.5, 0.5)
    assert M.macro_f1([0, 1, 2], [0, 1, 2], 3) == pytest.approx(1.0)


def test_null_ece_floor_is_small_and_floor_removes_zeros():
    from jevbench.followup import _floor, _null_ece
    rng = np.random.default_rng(6)
    conf = rng.uniform(0.5, 1.0, 1000)
    assert _null_ece(conf, rng) < 0.05
    P = np.array([[0.0, 0.99, 0.01], [0.5, 0.5, 0.0]])
    Q = _floor(P)
    assert (Q > 0).all() and np.allclose(Q.sum(axis=1), 1.0)
    assert Q.min() == pytest.approx(0.005 / (1 + 0.005), rel=1e-6)
