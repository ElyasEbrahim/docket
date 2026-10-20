"""Coverage tests for counts with error bars (ADR 0003: every stated guarantee is checked by simulation)."""
from statistics import NormalDist

import numpy as np
import pytest

from pgdocket.estimate import norm_ppf, ppi_share


def test_norm_ppf_matches_the_standard_library():
    for p in [1e-6, 0.001, 0.0125, 0.025, 0.05, 0.3, 0.5, 0.7, 0.95, 0.975, 0.9875, 0.999, 1 - 1e-6]:
        assert norm_ppf(p) == pytest.approx(NormalDist().inv_cdf(p), rel=1e-8, abs=1e-9)


def _population(rng, N, prevalence, fpr, fnr):
    y = rng.random(N) < prevalence
    flip = np.where(y, rng.random(N) < fnr, rng.random(N) < fpr)    # the model's mistakes depend on the truth
    return y.astype(float), np.where(flip, 1 - y, y).astype(float)


@pytest.mark.parametrize("prevalence,fpr,fnr,n", [(0.2, 0.05, 0.15, 150), (0.5, 0.2, 0.2, 150), (0.08, 0.02, 0.4, 300)])
def test_ppi_interval_covers_the_true_share_95_percent_of_the_time(prevalence, fpr, fnr, n):
    rng = np.random.default_rng(11)
    N, trials, hits, widths_ppi, widths_lab = 4000, 1000, 0, [], []
    for _ in range(trials):
        y, f = _population(rng, N, prevalence, fpr, fnr)
        lab = rng.choice(N, n, replace=False)
        mask = np.zeros(N, bool)
        mask[lab] = True
        r = ppi_share(f[~mask], f[mask], y[mask])
        assert r["reliable"] or min(r["labels_with"], r["labels_without"]) < 10
        hits += r["ci_low"] <= y.mean() <= r["ci_high"]
        widths_ppi.append(r["ci_high"] - r["ci_low"])
        widths_lab.append(r["labels_high"] - r["labels_low"])
    coverage = hits / trials
    assert 0.93 <= coverage <= 0.975, coverage           # nominal 95 %; ±1.5 points of Monte Carlo slack
    assert np.mean(widths_ppi) <= np.mean(widths_lab) * 1.02   # never meaningfully worse than labels only


def test_ppi_is_much_narrower_than_labels_alone_when_the_model_is_good():
    rng = np.random.default_rng(12)
    y, f = _population(rng, 5000, 0.3, 0.03, 0.05)
    lab = rng.choice(5000, 100, replace=False)
    mask = np.zeros(5000, bool)
    mask[lab] = True
    r = ppi_share(f[~mask], f[mask], y[mask])
    assert (r["ci_high"] - r["ci_low"]) < 0.6 * (r["labels_high"] - r["labels_low"])
    assert r["lam"] > 0.5


def test_useless_model_falls_back_to_labels_only():
    rng = np.random.default_rng(13)
    y = (rng.random(3000) < 0.4).astype(float)
    f = (rng.random(3000) < 0.5).astype(float)                # unrelated to the truth
    r = ppi_share(f[100:], f[:100], y[:100])
    assert r["lam"] < 0.3
    assert (r["ci_high"] - r["ci_low"]) <= (r["labels_high"] - r["labels_low"]) * 1.05


def test_biased_model_count_is_corrected():
    # The model over-counts positives (false positive rate 30 %); its raw share is far off, PPI isn't.
    rng = np.random.default_rng(14)
    y, f = _population(rng, 6000, 0.1, 0.30, 0.05)
    lab = rng.choice(6000, 200, replace=False)
    mask = np.zeros(6000, bool)
    mask[lab] = True
    r = ppi_share(f[~mask], f[mask], y[mask])
    assert abs(r["model_share"] - y.mean()) > 0.2
    assert r["ci_low"] <= y.mean() <= r["ci_high"]


def test_too_few_labels_on_one_side_is_flagged_unreliable():
    # A rare answer (8 %) and 150 labels: about a quarter of draws have < 10 positives, where coverage
    # drops to ~75 %. Those draws must be flagged; the flagged-reliable ones must keep their 95 %.
    rng = np.random.default_rng(21)
    reliable_hits, reliable_n, flagged = 0, 0, 0
    for _ in range(1000):
        y, f = _population(rng, 4000, 0.08, 0.02, 0.4)
        lab = rng.choice(4000, 150, replace=False)
        mask = np.zeros(4000, bool)
        mask[lab] = True
        r = ppi_share(f[~mask], f[mask], y[mask])
        if r["reliable"]:
            reliable_n += 1
            reliable_hits += r["ci_low"] <= y.mean() <= r["ci_high"]
        else:
            flagged += 1
    assert flagged > 100
    assert reliable_hits / reliable_n >= 0.93


def test_no_interval_without_a_labelled_example():
    r = ppi_share([1, 0, 0, 1] * 50, [0] * 40, [0] * 40)            # no labelled row has the answer
    assert r["estimate"] is None and r["ci_low"] is None and r["reliable"] is False
