"""Fit a one-parameter calibrator from human labels (ADR 0003) and apply it exactly as docket.calibrated() does in SQL.

choice: clamp exact zeros at half the smallest non-zero probability, then one temperature T.
noul:   Platt scaling, sigmoid(a * logit(p) + b).
The stored calibration also carries a threshold with a precision guarantee, chosen on out-of-fold scores.
"""
import math
from datetime import datetime, timezone

import numpy as np

from . import metrics as M
from .spec import choice_vector, option_display, option_names


def calibrated(answer, spec, cal):
    """Python twin of the SQL function docket.calibrated(answer, spec, cal)."""
    if answer is None:
        return None
    if spec["kind"] == "noul":
        p = float(answer["noul"])
        if not cal:
            return p
        p = min(max(p, 1e-6), 1 - 1e-6)
        return 1 / (1 + math.exp(-(cal["a"] * math.log(p / (1 - p)) + cal["b"])))
    probs = [float(v) for v in (answer.get("probabilities") or {}).values()]
    if not cal:
        return max(probs)
    t, f = cal["temperature"], cal.get("floor") or 0.0
    q = [max(p, f) for p in probs]
    return max(q) ** (1 / t) / sum(x ** (1 / t) for x in q)


def fit(spec, answers, labels, precision_target=0.9, alpha=0.05):
    """answers: raw backend answers; labels: option names (choice) or booleans (noul), same order."""
    n = len(labels)
    if n < 30:
        raise ValueError(f"only {n} labeled rows with answers; need at least 30 (100–200 recommended)")
    common = {"n_labels": n, "precision_target": precision_target, "alpha": alpha,
              "fitted_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    if spec["kind"] == "choice":
        names, display = option_names(spec), option_display(spec)
        P = np.array([choice_vector(a, display) for a in answers])
        y = np.array([names.index(l) for l in labels])
        floor = float(P[P > 0].min() / 2) if (P == 0).any() else 0.0
        Pf = np.maximum(P, floor)
        Pf = Pf / Pf.sum(axis=1, keepdims=True)
        T = M.temperature_fit(Pf, y)
        P_cv, _ = M.crossfit_temperature(Pf, y)
        conf_cv, correct_cv = P_cv.max(axis=1), (P_cv.argmax(axis=1) == y).astype(float)
        raw_conf, raw_correct = P.max(axis=1), (P.argmax(axis=1) == y).astype(float)
        cal = {"method": "temperature", "temperature": T, "floor": floor,
               "ece_raw": M.ece(raw_conf, raw_correct, 15), "ece_calibrated": M.ece(conf_cv, correct_cv, 15),
               "accuracy": float(raw_correct.mean())}
        score, ok = conf_cv, correct_cv
    else:
        p = np.array([float(a["noul"]) for a in answers])
        y = np.array([bool(l) for l in labels], float)
        a, b = M.platt_fit(p, y)
        p_cv = M.crossfit_binary(p, y, "platt")
        cal = {"method": "platt", "a": float(a), "b": float(b),
               "ece_raw": M.ece(p, y, 15), "ece_calibrated": M.ece(p_cv, y, 15), "prevalence": float(y.mean())}
        score, ok = p_cv, y
    th = M.precision_threshold(score, ok, precision_target, alpha)
    chosen = th["chosen"]
    cal.update(common, threshold=chosen["threshold"] if chosen else None,
               coverage=chosen["coverage"] if chosen else 0.0,
               observed_precision=chosen["precision"] if chosen else None)
    return cal
