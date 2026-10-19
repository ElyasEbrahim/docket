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


# ---------------------------------------------------------------- batch context
def batch_context_stats(same, shuffled, y, n_boot=1000, seed=0):
    """same: (k ≥ 3, rows, options) probabilities from runs with identical batches; shuffled: (rows, options) from a
    run where every row had different batch neighbours.

    Compares like with like. For each pair (i, j) of same-batch runs, take the rows where i and j agree.
    Noise: how often the remaining same-batch run k disagrees with them. Context: how often the shuffled run does.
    Both use the same rows, so the per-row difference isolates the effect of the neighbours.
    """
    k = same.shape[0]
    top_same, top_s = same.argmax(axis=2), shuffled.argmax(axis=1)
    diffs, noise_rates, ctx_rates = [], [], []
    for i, j in combinations(range(k), 2):
        rest = [m for m in range(k) if m not in (i, j)]
        agree = top_same[i] == top_same[j]
        for m in rest:
            noise = (top_same[m][agree] != top_same[i][agree]).astype(float)
            ctx = (top_s[agree] != top_same[i][agree]).astype(float)
            noise_rates.append(noise.mean())
            ctx_rates.append(ctx.mean())
            diffs.append(ctx - noise)
    diff = np.concatenate(diffs)
    # probability movement: shuffled vs each same-batch run, against same-batch runs vs each other
    move_ctx = np.mean([np.abs(shuffled - same[i]).max(axis=1).mean() for i in range(k)])
    move_noise = np.mean([np.abs(same[i] - same[j]).max(axis=1).mean() for i, j in combinations(range(k), 2)])
    flips_ctx = [float((top_s != top_same[i]).mean()) for i in range(k)]
    flips_noise = [float((top_same[i] != top_same[j]).mean()) for i, j in combinations(range(k), 2)]
    return {
        "rows": int(len(y)),
        "disagreement_noise": float(np.mean(noise_rates)), "disagreement_shuffled": float(np.mean(ctx_rates)),
        "excess_disagreement": float(diff.mean()),
        "excess_disagreement_ci": M.bootstrap_ci(np.mean, [diff], n_boot=n_boot, seed=seed),
        "pairwise_flips_same_batches": flips_noise, "pairwise_flips_shuffled_vs_same": flips_ctx,
        "mean_max_prob_change_same_batches": float(move_noise), "mean_max_prob_change_shuffled": float(move_ctx),
        "accuracy_same": [float((top_same[i] == y).mean()) for i in range(k)],
        "accuracy_shuffled": float((top_s == y).mean()),
        "ece_same": [M.ece(same[i].max(axis=1), (top_same[i] == y).astype(float), 15) for i in range(k)],
        "ece_shuffled": M.ece(shuffled.max(axis=1), (top_s == y).astype(float), 15),
    }


def batch_context(same_runs, shuffled_run, experiment="choice_base", reorder_info=None):
    with connect() as conn:
        runs = [load_run(conn, r) for r in same_runs + [shuffled_run]]
    truth = runs[0][3]
    opts = list(runs[0][1][experiment]["options"])
    common = sorted(set.intersection(*(set(a[experiment]) for _, _, a, _ in runs)))
    P = np.stack([[choice_probs(a[experiment][h], opts)[0] for h in common] for _, _, a, _ in runs])
    y = np.array([opts.index(truth[h].product) for h in common])
    out = batch_context_stats(P[:-1], P[-1], y)
    out.update({"experiment": experiment, "same_batch_runs": same_runs, "shuffled_run": shuffled_run,
                "reorder": reorder_info})
    return out


def render_batch_context(b):
    pct = lambda x: f"{100 * x:.1f} %"
    lo, hi = b["excess_disagreement_ci"]
    r = b.get("reorder") or {}
    L = [f"# Batch context: `{b['experiment']}`", "",
         f"Same-batch runs: {', '.join(f'`{x}`' for x in b['same_batch_runs'])}. Shuffled-batch run: `{b['shuffled_run']}`. "
         f"{b['rows']} rows, same options, same model; only each row's 19 batch neighbours differ."]
    if r:
        L += ["", f"After reordering, {pct(r['rows_with_no_shared_neighbour'])} of rows share no neighbour with their "
                  f"original batch (mean shared neighbours {r['mean_shared_neighbours']:.2f} of 19)."]
    L += ["", "| measure | same batches (noise) | shuffled batches |", "| --- | ---: | ---: |",
          f"| disagreement with a pair of same-batch runs that agree | {pct(b['disagreement_noise'])} | {pct(b['disagreement_shuffled'])} |",
          f"| pairwise top-1 flips | {', '.join(pct(x) for x in b['pairwise_flips_same_batches'])} | "
          f"{', '.join(pct(x) for x in b['pairwise_flips_shuffled_vs_same'])} |",
          f"| mean largest probability change per row | {b['mean_max_prob_change_same_batches']:.4f} | {b['mean_max_prob_change_shuffled']:.4f} |",
          f"| accuracy | {', '.join(pct(x) for x in b['accuracy_same'])} | {pct(b['accuracy_shuffled'])} |",
          f"| top-label ECE | {', '.join(f'{x:.3f}' for x in b['ece_same'])} | {b['ece_shuffled']:.3f} |", "",
          f"**Excess disagreement caused by different neighbours:** {100 * b['excess_disagreement']:+.2f} pp "
          f"[{100 * lo:+.2f}, {100 * hi:+.2f}] (95 % bootstrap CI over rows). A CI that includes 0 means the batch "
          "context effect is not distinguishable from run-to-run noise."]
    return "\n".join(L) + "\n"


# ---------------------------------------------------------------- batch size
def _calibrated_ece(P, y):
    Pf = _floor(P)
    Q, T = M.crossfit_temperature(Pf, y)
    conf, correct = P.max(axis=1), (P.argmax(axis=1) == y).astype(float)
    return {"ece": M.ece(conf, correct, 15), "temperature": T,
            "ece_after_temperature": M.ece(Q.max(axis=1), (Q.argmax(axis=1) == y).astype(float), 15),
            "ece_after_isotonic": M.ece(M.crossfit_binary(conf, correct, "isotonic"), correct, 15),
            "exact_zeros": int((P == 0).sum()), "rows_label_prob_zero": int((P[np.arange(len(y)), y] == 0).sum())}


def batch_size_compare(batched_runs, single_run, shuffled_run=None, experiment="choice_base"):
    """Single-row judging vs pg-jev's 20-row batches on the same rows, options and model."""
    names = batched_runs + [single_run] + ([shuffled_run] if shuffled_run else [])
    with connect() as conn:
        runs = {r: load_run(conn, r) for r in names}
    truth = runs[single_run][3]
    opts = list(runs[single_run][1][experiment]["options"])
    common = sorted(set.intersection(*(set(runs[r][2][experiment]) for r in names)))
    P = {r: np.array([choice_probs(runs[r][2][experiment][h], opts)[0] for h in common]) for r in names}
    y = np.array([opts.index(truth[h].product) for h in common])
    Pb = np.stack([P[r] for r in batched_runs])
    out = {"experiment": experiment, "batched_runs": batched_runs, "single_run": single_run, "rows": len(common)}
    out["disagreement"] = batch_context_stats(Pb, P[single_run], y)
    correct_b = (Pb.argmax(axis=2) == y).astype(float)                     # (runs, rows)
    correct_s = (P[single_run].argmax(axis=1) == y).astype(float)
    gain = correct_s - correct_b.mean(axis=0)
    out["accuracy_single"] = float(correct_s.mean())
    out["accuracy_batched"] = [float(c.mean()) for c in correct_b]
    out["accuracy_gain"] = float(gain.mean())
    out["accuracy_gain_ci"] = M.bootstrap_ci(np.mean, [gain])
    out["macro_f1_single"] = M.macro_f1(P[single_run].argmax(axis=1), y, len(opts))
    out["macro_f1_batched"] = [M.macro_f1(p.argmax(axis=1), y, len(opts)) for p in Pb]
    out["calibration_single"] = _calibrated_ece(P[single_run], y)
    out["calibration_batched"] = _calibrated_ece(P[batched_runs[0]], y)
    out["per_class_recall"] = [
        {"option": o, "n": int((y == c).sum()),
         "single": float(correct_s[y == c].mean()) if (y == c).any() else None,
         "batched": float(correct_b[:, y == c].mean()) if (y == c).any() else None}
        for c, o in enumerate(opts)]
    meta = {r: runs[r][1][experiment] for r in (batched_runs[0], single_run)}
    out["cost"] = {r: {"seconds": float(meta[r]["seconds"]), "requests": int(meta[r]["stats"].get("requests", 0)),
                       "input_tokens": int(meta[r]["stats"].get("input_tokens", 0)),
                       "usd": float(meta[r]["stats"].get("estimated_cost_usd", 0))} for r in meta}
    if shuffled_run:
        top_b = Pb.argmax(axis=2)
        stable = np.all(top_b == top_b[0], axis=0)
        cons, shuf, single = top_b[0], P[shuffled_run].argmax(axis=1), P[single_run].argmax(axis=1)
        flipped = stable & (shuf != cons)
        out["context_sensitive_rows"] = {
            "n": int(flipped.sum()),
            "single_agrees_with_original_batches": float((single[flipped] == cons[flipped]).mean()),
            "single_agrees_with_shuffled_batches": float((single[flipped] == shuf[flipped]).mean()),
            "single_correct": float((single[flipped] == y[flipped]).mean()),
            "original_batches_correct": float((cons[flipped] == y[flipped]).mean()),
            "shuffled_batches_correct": float((shuf[flipped] == y[flipped]).mean()),
        }
    return out


def render_batch_size(b):
    pct = lambda x: f"{100 * x:.1f} %"
    d, cs, cb = b["disagreement"], b["calibration_single"], b["calibration_batched"]
    lo, hi = b["accuracy_gain_ci"]
    rs, rb = b["cost"][b["single_run"]], b["cost"][b["batched_runs"][0]]
    L = [f"# Batch size 1 vs 20: `{b['experiment']}`", "",
         f"Batched (20 rows per request): {', '.join(f'`{r}`' for r in b['batched_runs'])}. "
         f"Single-row: `{b['single_run']}`. {b['rows']} rows, same options and model.", "",
         "| measure | 20 rows per request | 1 row per request |", "| --- | ---: | ---: |",
         f"| accuracy | {', '.join(pct(x) for x in b['accuracy_batched'])} | {pct(b['accuracy_single'])} |",
         f"| macro-F1 | {', '.join(f'{x:.3f}' for x in b['macro_f1_batched'])} | {b['macro_f1_single']:.3f} |",
         f"| top-label ECE (raw) | {cb['ece']:.3f} | {cs['ece']:.3f} |",
         f"| ECE after floored temperature (T) | {cb['ece_after_temperature']:.3f} ({cb['temperature']:.2f}) | "
         f"{cs['ece_after_temperature']:.3f} ({cs['temperature']:.2f}) |",
         f"| ECE after isotonic | {cb['ece_after_isotonic']:.3f} | {cs['ece_after_isotonic']:.3f} |",
         f"| exact zeros / rows where the label gets 0 | {cb['exact_zeros']:,} / {cb['rows_label_prob_zero']} | "
         f"{cs['exact_zeros']:,} / {cs['rows_label_prob_zero']} |",
         f"| requests / input tokens | {rb['requests']} / {rb['input_tokens']:,} | {rs['requests']} / {rs['input_tokens']:,} |",
         f"| tokens per row / cost per 1,000 rows | {rb['input_tokens'] / b['rows']:.0f} / ${1000 * rb['usd'] / b['rows']:.4f} | "
         f"{rs['input_tokens'] / b['rows']:.0f} / ${1000 * rs['usd'] / b['rows']:.4f} |",
         f"| wall-clock for {b['rows']} rows | {rb['seconds']:.1f} s | {rs['seconds']:.1f} s |", "",
         f"**Accuracy change from judging rows singly:** {100 * b['accuracy_gain']:+.2f} pp [{100 * lo:+.2f}, {100 * hi:+.2f}] "
         "(paired per row against the mean of the batched runs; 95 % bootstrap CI).", "",
         "| disagreement | value |", "| --- | ---: |",
         f"| between batched runs (noise) | {', '.join(pct(x) for x in d['pairwise_flips_same_batches'])} |",
         f"| single-row vs each batched run | {', '.join(pct(x) for x in d['pairwise_flips_shuffled_vs_same'])} |",
         f"| excess over noise | {100 * d['excess_disagreement']:+.2f} pp [{100 * d['excess_disagreement_ci'][0]:+.2f}, "
         f"{100 * d['excess_disagreement_ci'][1]:+.2f}] |", ""]
    c = b.get("context_sensitive_rows")
    if c:
        L += [f"On the {c['n']} rows whose answer flipped when re-batched (#3), single-row judging agrees with the "
              f"original batches {pct(c['single_agrees_with_original_batches'])} and with the shuffled batches "
              f"{pct(c['single_agrees_with_shuffled_batches'])} of the time. Correct: original batches "
              f"{pct(c['original_batches_correct'])}, shuffled {pct(c['shuffled_batches_correct'])}, single-row "
              f"{pct(c['single_correct'])}.", ""]
    L += ["| class | rows | recall, 20 per request | recall, 1 per request |", "| --- | ---: | ---: | ---: |"]
    L += [f"| {r['option']} | {r['n']} | {pct(r['batched'])} | {pct(r['single'])} |" for r in b["per_class_recall"]]
    return "\n".join(L) + "\n"


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
