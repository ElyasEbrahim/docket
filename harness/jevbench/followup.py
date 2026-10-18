"""Follow-up analyses on stored runs (no API calls).

determinism     compare the same experiment across repeated runs: do identical requests get identical answers?
learning_curve  how many labels does a calibrator need? Fit on n random labels, score ECE on 1,000 held-out rows.
"""
import json
import os
from itertools import combinations

import numpy as np

from . import metrics as M
from .db import connect
from .report import choice_probs, load_run
from .tasks import noul_truth


# ---------------------------------------------------------------- determinism
def determinism(run_ids, experiment="choice_base"):
    with connect() as conn:
        runs = [load_run(conn, r) for r in run_ids]
    truth = runs[0][3]
    opts = list(runs[0][1][experiment]["options"])
    for _, exps, _, _ in runs[1:]:
        if list(exps[experiment]["options"]) != opts:
            raise SystemExit("runs used different options for " + experiment)
    common = sorted(set.intersection(*(set(a[experiment]) for _, _, a, _ in runs)))
    P = np.stack([[choice_probs(a[experiment][h], opts)[0] for h in common] for _, _, a, _ in runs])  # (runs, rows, k)
    y = np.array([opts.index(truth[h].product) for h in common])
    top = P.argmax(axis=2)
    identical_probs = np.all(np.abs(P - P[0]) < 1e-9, axis=(0, 2))
    identical_top = np.all(top == top[0], axis=0)
    spread = (P.max(axis=0) - P.min(axis=0)).max(axis=1)             # per row: largest change of any option
    conf0 = P[0].max(axis=1)
    pairs = []
    for i, j in combinations(range(len(runs)), 2):
        d = np.abs(P[i] - P[j]).max(axis=1)
        pairs.append({"a": run_ids[i], "b": run_ids[j],
                      "top1_agreement": float((top[i] == top[j]).mean()),
                      "identical_probabilities": float((d < 1e-9).mean()),
                      "rows_max_abs_diff_ge_0.05": float((d >= 0.05 - 1e-9).mean()),
                      "mean_max_abs_diff": float(d.mean())})
    per_run = [{"run": r, "accuracy": float((top[k] == y).mean()),
                "ece": M.ece(P[k].max(axis=1), (top[k] == y).astype(float), 15)} for k, r in enumerate(run_ids)]
    flipped = ~identical_top
    return {
        "experiment": experiment, "runs": run_ids, "n": len(common),
        "rows_identical_probabilities_all_runs": float(identical_probs.mean()),
        "rows_identical_top1_all_runs": float(identical_top.mean()),
        "rows_any_option_moves_ge_0.05": float((spread >= 0.05 - 1e-9).mean()),
        "max_probability_change_seen": float(spread.max()),
        "mean_confidence_flipped_rows": float(conf0[flipped].mean()) if flipped.any() else None,
        "mean_confidence_stable_rows": float(conf0[~flipped].mean()),
        "pairs": pairs, "per_run": per_run,
        "spread_histogram": {f"{lo:.2f}-{hi:.2f}": int(((spread >= lo - 1e-9) & (spread < hi - 1e-9)).sum())
                             for lo, hi in [(0, 0.01), (0.01, 0.02), (0.02, 0.05), (0.05, 0.1), (0.1, 0.2), (0.2, 1.01)]},
    }


# ---------------------------------------------------------------- learning curve
def _choice_arrays(exps, answers, truth, name):
    opts = list(exps[name]["options"])
    hs = sorted(answers[name])
    P = np.array([choice_probs(answers[name][h], opts)[0] for h in hs])
    y = np.array([opts.index(truth[h].product) for h in hs])
    return P, y


def _floor(P):
    zeros = (P == 0).any()
    if not zeros:
        return P
    f = P[P > 0].min() / 2
    Q = np.maximum(P, f)
    return Q / Q.sum(axis=1, keepdims=True)


def _null_ece(conf, rng, draws=50):
    """ECE a perfectly calibrated predictor with these confidences would show on this many rows (finite-sample floor)."""
    return float(np.mean([M.ece(conf, (rng.random(len(conf)) < conf).astype(float), 15) for _ in range(draws)]))


def learning_curve(run_id, sizes=(100, 200, 500, 1000), repeats=50, test_size=1000, seed=0):
    with connect() as conn:
        _, exps, answers, truth = load_run(conn, run_id)
    rng = np.random.default_rng(seed)
    out = {"run": run_id, "sizes": list(sizes), "repeats": repeats, "test_size": test_size, "tasks": {}}

    if "choice_base" in exps:
        P, y = _choice_arrays(exps, answers, truth, "choice_base")
        Pf = _floor(P)
        conf, correct = P.max(axis=1), (P.argmax(axis=1) == y).astype(float)
        rows = {n: {"isotonic": [], "temperature": [], "raw": []} for n in sizes}
        for _ in range(repeats):
            perm = rng.permutation(len(y))
            test, pool = perm[:test_size], perm[test_size:]
            for n in sizes:
                cal = pool[:n]
                iso = M.isotonic_predict(M.isotonic_fit(conf[cal], correct[cal]), conf[test])
                rows[n]["isotonic"].append(M.ece(iso, correct[test], 15))
                T = M.temperature_fit(Pf[cal], y[cal])
                Q = M.temperature_apply(Pf[test], T)
                rows[n]["temperature"].append(M.ece(Q.max(axis=1), (Q.argmax(axis=1) == y[test]).astype(float), 15))
                rows[n]["raw"].append(M.ece(conf[test], correct[test], 15))
        conf_cal = M.crossfit_binary(conf, correct, "isotonic")
        out["tasks"]["choice_base"] = {
            "metric": "top-label ECE", "floor": _null_ece(conf_cal[:test_size], rng),
            "curve": {n: {k: _summ(v) for k, v in r.items()} for n, r in rows.items()}}

    for name, e in exps.items():
        if e["kind"] != "noul":
            continue
        hs = sorted(answers[name])
        p = np.array([float(answers[name][h]["noul"]) for h in hs])
        yy = np.array([noul_truth(e["family"], truth[h]) for h in hs], float)
        rows = {n: {"isotonic": [], "platt": [], "raw": [], "positives_in_labels": []} for n in sizes}
        for _ in range(repeats):
            perm = rng.permutation(len(yy))
            test, pool = perm[:test_size], perm[test_size:]
            for n in sizes:
                cal = pool[:n]
                rows[n]["isotonic"].append(M.ece(M.isotonic_predict(M.isotonic_fit(p[cal], yy[cal]), p[test]), yy[test], 15))
                rows[n]["platt"].append(M.ece(M.platt_predict(M.platt_fit(p[cal], yy[cal]), p[test]), yy[test], 15))
                rows[n]["raw"].append(M.ece(p[test], yy[test], 15))
                rows[n]["positives_in_labels"].append(float(yy[cal].sum()))
        iso_all = M.crossfit_binary(p, yy, "isotonic")
        out["tasks"][name] = {
            "metric": "ECE", "prevalence": float(yy.mean()), "floor": _null_ece(iso_all[:test_size], rng),
            "curve": {n: {k: _summ(v) for k, v in r.items()} for n, r in rows.items()}}
    return out


def _summ(v):
    v = np.asarray(v, float)
    return {"mean": float(v.mean()), "p10": float(np.quantile(v, 0.1)), "p90": float(np.quantile(v, 0.9))}


# ---------------------------------------------------------------- rendering
def _f(x, d=3):
    return "–" if x is None else f"{x:.{d}f}"


def render_determinism(d):
    L = [f"# Run-to-run determinism: `{d['experiment']}`", "",
         f"Runs: {', '.join(f'`{r}`' for r in d['runs'])} · {d['n']} rows · identical requests (same rows, order, "
         "batches, options and model).", "",
         "| metric | value |", "| --- | ---: |",
         f"| rows with identical probabilities in every run | {100 * d['rows_identical_probabilities_all_runs']:.1f} % |",
         f"| rows with the same top answer in every run | {100 * d['rows_identical_top1_all_runs']:.1f} % |",
         f"| rows where some option moves by ≥ 0.05 | {100 * d['rows_any_option_moves_ge_0.05']:.1f} % |",
         f"| largest probability change seen | {_f(d['max_probability_change_seen'], 2)} |",
         f"| mean confidence (first run): rows whose answer flips / stable rows | {_f(d['mean_confidence_flipped_rows'])} / {_f(d['mean_confidence_stable_rows'])} |",
         "", "| run pair | top-1 agreement | identical probabilities | rows with max change ≥ 0.05 | mean max change |",
         "| --- | ---: | ---: | ---: | ---: |"]
    L += [f"| `{p['a']}` vs `{p['b']}` | {100 * p['top1_agreement']:.1f} % | {100 * p['identical_probabilities']:.1f} % | "
          f"{100 * p['rows_max_abs_diff_ge_0.05']:.1f} % | {_f(p['mean_max_abs_diff'], 4)} |" for p in d["pairs"]]
    L += ["", "| run | accuracy | ECE |", "| --- | ---: | ---: |"]
    L += [f"| `{r['run']}` | {100 * r['accuracy']:.1f} % | {_f(r['ece'])} |" for r in d["per_run"]]
    L += ["", "Largest change of any option probability per row, across runs:", "",
          "| change | rows |", "| --- | ---: |"]
    L += [f"| {k} | {v} |" for k, v in d["spread_histogram"].items()]
    return "\n".join(L) + "\n"


def render_curve(c):
    L = [f"# Label learning curve: run `{c['run']}`", "",
         f"For each label budget n, fit the calibrator on n random labeled rows and measure ECE on {c['test_size']} "
         f"other rows. {c['repeats']} random splits per n; values are mean [10th–90th percentile]. "
         "\"Floor\" is the ECE a perfectly calibrated predictor would still show on this many test rows (finite-sample noise).", ""]
    for name, t in c["tasks"].items():
        methods = [k for k in next(iter(t["curve"].values())) if k not in ("raw", "positives_in_labels")]
        L += [f"## `{name}`" + (f" (prevalence {100 * t['prevalence']:.1f} %)" if "prevalence" in t else ""), "",
              "| labels | raw | " + " | ".join(methods) + (" | positives among labels |" if "prevalence" in t else " |"),
              "| ---: | ---: | " + " | ".join("---:" for _ in methods) + (" | ---: |" if "prevalence" in t else " |")]
        for n, r in t["curve"].items():
            cells = [f"{r[m]['mean']:.3f} [{r[m]['p10']:.3f}–{r[m]['p90']:.3f}]" for m in methods]
            extra = f" | {r['positives_in_labels']['mean']:.0f}" if "prevalence" in t else ""
            L.append(f"| {n} | {r['raw']['mean']:.3f} | " + " | ".join(cells) + extra + " |")
        L += ["", f"Finite-sample floor on {c['test_size']} rows: {t['floor']:.3f}", ""]
    return "\n".join(L)


def write(obj, md, out_path):
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path + ".json", "w") as f:
        json.dump(obj, f, indent=2, default=float)
    with open(out_path + ".md", "w") as f:
        f.write(md)
    return out_path + ".md"
