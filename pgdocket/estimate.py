"""Counts with error bars: prediction-powered inference (PPI++) for the share of rows with a given true label.

The model has answered every row; humans have labelled a *random sample* of them. Two honest estimates exist:

- labels only: the share among the labelled rows. Unbiased, but wide when there are few labels.
- PPI++: the model's share on the unlabelled rows, corrected by how the model disagreed with the labels.
  Unbiased for any model, and narrower when the model is good. The power-tuning weight `lambda` (0..1)
  makes it never worse than labels only: lambda = 0 *is* labels only, lambda = 1 is classic PPI.

  theta  = mean(y_l) + lambda * (mean(f_u) - mean(f_l))
  var    = var(y_l - lambda f_l) / n + lambda^2 var(f_u) / N_u
  lambda = cov(y_l, f_l) / ((1 + n / N_u) var(f)), clipped to [0, 1]

References: Angelopoulos, Bates, Fannjiang, Jordan, Zrnic, "Prediction-powered inference", Science 2023;
Angelopoulos, Duchi, Zrnic, "PPI++: Efficient prediction-powered inference", 2023.
Validity needs the labelled rows to be a uniform random sample of the rows being estimated (ADR 0003).
The interval is a normal approximation: simulations show it holds (≈ 95 %) once the labels contain at least
MIN_EACH_SIDE examples with and without the answer, and can fall well short with fewer (75 % at 5–9). Estimates
below that are returned but marked `reliable = False`.
The SQL function docket.estimate() implements the same formulas; tests check they agree.
"""
import math

import numpy as np

MIN_EACH_SIDE = 10


def norm_ppf(p):
    """Inverse standard normal CDF (Acklam's rational approximation, relative error < 1.2e-9).
    Same algorithm as docket.norm_ppf() in SQL, so both give identical intervals."""
    a = [-3.969683028665376e+01, 2.209460984245205e+02, -2.759285104469687e+02, 1.383577518672690e+02,
         -3.066479806614716e+01, 2.506628277459239e+00]
    b = [-5.447609879822406e+01, 1.615858368580409e+02, -1.556989798598866e+02, 6.680131188771972e+01,
         -1.328068155288572e+01]
    c = [-7.784894002430293e-03, -3.223964580411365e-01, -2.400758277161838e+00, -2.549732539343734e+00,
         4.374664141464968e+00, 2.938163982698783e+00]
    d = [7.784695709041462e-03, 3.224671290700398e-01, 2.445134137142996e+00, 3.754408661907416e+00]
    lo = 0.02425
    if p < lo:
        q = math.sqrt(-2 * math.log(p))
        return (((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / \
               ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1)
    if p > 1 - lo:
        return -norm_ppf(1 - p)
    q = p - 0.5
    r = q * q
    return (((((a[0] * r + a[1]) * r + a[2]) * r + a[3]) * r + a[4]) * r + a[5]) * q / \
           (((((b[0] * r + b[1]) * r + b[2]) * r + b[3]) * r + b[4]) * r + 1)


def _var(x):
    return float(np.var(x, ddof=1)) if len(x) > 1 else float("nan")


def ppi_share(f_unlabeled, f_labeled, y_labeled, level=0.95):
    """Estimate the share of rows whose true label is positive.

    f_*: the model's answer as 0/1 (or a probability) on unlabelled / labelled rows; y_labeled: the human label 0/1.
    Returns the PPI++ estimate and interval, the labels-only interval, and the model-only share, all as shares.
    """
    fu, fl, y = (np.asarray(x, float) for x in (f_unlabeled, f_labeled, y_labeled))
    n, nu = len(y), len(fu)
    z = norm_ppf(0.5 + level / 2)
    out = {"n_labels": n, "n_unlabeled": nu, "level": level,
           "model_share": float(np.concatenate([fu, fl]).mean()) if n + nu else float("nan")}
    if n < 2:
        out.update(estimate=None, ci_low=None, ci_high=None, labels_low=None, labels_high=None, lam=None, se=None,
                   reliable=False)
        return out
    k = int(round(float(y.sum())))
    out.update(labels_with=k, labels_without=n - k, reliable=min(k, n - k) >= MIN_EACH_SIDE)
    if k == 0 or k == n:
        # No labelled example on one side: nothing tells us how often the model is wrong there. No interval.
        out.update(estimate=None, ci_low=None, ci_high=None, labels_low=None, labels_high=None, lam=None, se=None)
        return out
    mean_y = float(y.mean())
    var_y = _var(y)
    se_labels = math.sqrt(var_y / n)
    out.update(labels_share=mean_y, labels_low=max(0.0, mean_y - z * se_labels), labels_high=min(1.0, mean_y + z * se_labels))
    if nu < 2:                                     # (almost) everything labelled: the labels are the answer
        out.update(estimate=mean_y, ci_low=out["labels_low"], ci_high=out["labels_high"], lam=0.0, se=se_labels)
        return out
    var_f = _var(np.concatenate([fu, fl]))
    cov_yf = float(np.cov(y, fl, ddof=1)[0, 1])
    lam = 0.0 if var_f <= 0 else min(1.0, max(0.0, cov_yf / ((1 + n / nu) * var_f)))
    theta = mean_y + lam * (float(fu.mean()) - float(fl.mean()))
    var_theta = (var_y + lam ** 2 * _var(fl) - 2 * lam * cov_yf) / n + lam ** 2 * _var(fu) / nu
    se = math.sqrt(max(var_theta, 0.0))
    out.update(estimate=theta, ci_low=max(0.0, theta - z * se), ci_high=min(1.0, theta + z * se), lam=lam, se=se)
    return out
