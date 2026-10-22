"""Test ideas from recent research on answers we already have (no API calls). Written up in docs/research/.

1. Per-answer precision: does the overall guarantee hide answers that are much less precise? (class-conditional /
   Mondrian guarantees: Ding et al., NeurIPS 2023)
2. Re-running `calibrate` as labels arrive and stopping at the first threshold found: does the 95 % guarantee hold?
   (anytime-valid risk control: Xu et al., NeurIPS 2024; here the simplest fix, alpha spent across looks)
3. Choosing which rows to label for counts: uncertainty-guided vs uniform sampling at the same budget
   (active statistical inference: Zrnic & Candès 2024; robust mixing: Li, Zrnic & Candès, NeurIPS 2025)
4. Review planning: how many rows must people review so the whole column's error is ≤ epsilon, with 95 % confidence
   (probably approximately correct labels: Candès, Ilyas & Zrnic 2025)
5. Asking twice and averaging: is the accuracy gain worth the cost? (three identical CFPB runs from Phase 0)
"""
import json
import math
import os

import numpy as np

from pgdocket import metrics as M
from pgdocket.spec import choice_vector, option_display, option_names

from .db import connect

OUT = "results/frontier-2026-10"


def load_check(folder):
    """Stored `pgdocket check` answers: probability matrix, predicted and true answer, raw top score."""
    cfg = json.load(open(f"results/{folder}/report.json"))["config"]
    rows = [json.loads(line) for line in open(f"results/{folder}/judgments.jsonl")]
    spec = {"kind": "choice", "question": cfg["question"], "options": cfg["options"]}
    names = option_names(spec)
    P = np.array([choice_vector(r["answer"], option_display(spec)) for r in rows])
    pred = np.array([names[i] for i in P.argmax(axis=1)])
    label = np.array([r["label"] for r in rows])
    return {"names": names, "P": P, "pred": pred, "label": label, "score": P.max(axis=1),
            "correct": (pred == label).astype(float)}


# ---------------------------------------------------------------- 1. per-answer precision
def per_answer(d, target, alpha=0.05):
    score, correct, pred = d["score"], d["correct"], d["pred"]
    ch = M.precision_threshold(score, correct, target, alpha)["chosen"]
    out = {"target": target, "overall": None, "answers": []}
    if ch:
        acc = score >= ch["threshold"]
        out["overall"] = {"threshold": ch["threshold"], "auto_share": float(acc.mean()), "precision": float(correct[acc].mean())}
    mondrian_accepted = 0
    for a in d["names"]:
        m = pred == a
        row = {"answer": a, "answered": int(m.sum())}
        if ch:
            am = acc & m
            k, n = int(correct[am].sum()), int(am.sum())
            row.update(auto=n, precision=k / n if n else None, lower=M.clopper_pearson_lower(k, n, alpha) if n else None)
        own = M.precision_threshold(score[m], correct[m], target, alpha)["chosen"] if m.sum() else None
        row["own_threshold_share"] = own["coverage"] if own else 0.0            # its own guarantee, within the answer
        mondrian_accepted += int(round(own["coverage"] * m.sum())) if own else 0
        out["answers"].append(row)
    out["mondrian_auto_share"] = mondrian_accepted / len(score)
    return out


# ---------------------------------------------------------------- 2. re-running calibrate as labels arrive
def optional_stopping(d, target, trials=1000, alpha=0.05, looks=range(30, 301, 10), seed=0):
    """Labels arrive 10 at a time (drawn with replacement: the 500 rows stand for a large population). After each
    batch the threshold is refitted; the user deploys the first one found. Failure: its true precision < target."""
    rng = np.random.default_rng(seed)
    score, correct = d["score"], d["correct"]
    true_prec = lambda t: correct[score >= t].mean()
    looks = list(looks)
    res = {"single look at 150": [], "single look at 300": [], "stop at first threshold": [],
           "stop at first, alpha spent over looks": []}
    for _ in range(trials):
        idx = rng.integers(0, len(score), looks[-1])
        first = spent = None
        for k, n in enumerate(looks, 1):
            s, c = score[idx[:n]], correct[idx[:n]]
            if first is None:
                ch = M.precision_threshold(s, c, target, alpha)["chosen"]
                first = ch["threshold"] if ch else None
            if spent is None:
                ch = M.precision_threshold(s, c, target, alpha * 6 / (math.pi ** 2 * k ** 2))["chosen"]
                spent = ch["threshold"] if ch else None
            if n in (150, looks[-1]):
                ch = M.precision_threshold(s, c, target, alpha)["chosen"]
                res[f"single look at {n}"].append(ch["threshold"] if ch else None)
        res["stop at first threshold"].append(first)
        res["stop at first, alpha spent over looks"].append(spent)
    out = {"target": target, "trials": trials}
    for name, ts in res.items():
        found = [t for t in ts if t is not None]
        fails = sum(true_prec(t) < target for t in found)
        # the guarantee bounds P(a bad threshold is deployed) over all trials, not among those that found one
        out[name] = {"found": len(found) / trials, "failure_probability": fails / trials,
                     "failure_among_found": fails / max(len(found), 1),
                     "median_auto_share": float(np.median([(score >= t).mean() for t in found])) if found else 0.0}
    return out


# ---------------------------------------------------------------- 3. which rows to label for counts
def active_counts(d, answers, budgets=(50, 100, 150), draws=2000, seed=0, floor=0.02):
    """Horvitz-Thompson difference estimator of the share with answer c, f = model says c, rows labelled
    independently with known probability pi_i. Uniform: pi = budget/N. Active: pi ∝ 1 - top score (+ floor)."""
    rng = np.random.default_rng(seed)
    N = len(d["score"])
    u = 1 - d["score"] + floor
    out = {}
    for c in answers:
        f, y = (d["pred"] == c).astype(float), (d["label"] == c).astype(float)
        truth = y.mean()
        res = {}
        for b in budgets:
            designs = {"uniform": np.full(N, b / N), "active": np.minimum(1, b * u / u.sum())}
            designs["robust (½ uniform + ½ active)"] = 0.5 * designs["uniform"] + 0.5 * designs["active"]
            for name, pi in designs.items():
                hit, width = 0, []
                for _ in range(draws):
                    xi = rng.random(N) < pi
                    r = (y - f) * xi / pi
                    est = f.mean() + r.mean()
                    var = (((y - f) ** 2) * xi * (1 - pi) / pi ** 2).sum() / N ** 2
                    h = 1.96 * math.sqrt(var)
                    hit += est - h <= truth <= est + h
                    width.append(2 * h)
                res.setdefault(name, {})[b] = {"coverage": hit / draws, "width_rows": float(np.mean(width) * N)}
        out[c] = {"true_count": int(y.sum()), "model_count": int(f.sum()), "by_design": res}
    return out


# ---------------------------------------------------------------- 4. review planning with a guarantee
def review_plan(d, eps, label_budgets=(100, 200), trials=1000, alpha=0.05, seed=0):
    """Keep AI answers with score ≥ s, people review the rest. L(s) = share of all rows that are kept AND wrong.
    From n labels drawn uniformly (with replacement) the one-sided Clopper-Pearson upper bound on L(s) is valid for each
    s; L is monotone in s, so lowering s until the bound exceeds eps needs no correction (PAC labels)."""
    rng = np.random.default_rng(seed)
    score, wrong = d["score"], 1 - d["correct"]
    cands = np.unique(score)[::-1]
    L = lambda s: float((wrong * (score >= s)).mean())
    oracle = next((float((score < s).mean()) for s in cands[::-1] if L(s) <= eps), 1.0)    # least review that works
    out = {"eps": eps, "ai_only_error": float(wrong.mean()), "oracle_review_share": oracle}
    for n in label_budgets:
        reviews, fails = [], 0
        for _ in range(trials):
            idx = rng.integers(0, len(score), n)
            s_ok = np.inf
            for s in cands:
                k = int((wrong[idx] * (score[idx] >= s)).sum())
                if 1 - M.clopper_pearson_lower(n - k, n, alpha) > eps:              # upper bound on L(s)
                    break
                s_ok = s
            reviews.append(float((score < s_ok).mean()))
            fails += L(s_ok) > eps
        out[n] = {"mean_review_share": float(np.mean(reviews)), "failure_rate": fails / trials}
    return out


# ---------------------------------------------------------------- 5. asking twice
def ensembling():
    from .report import choice_probs, load_run
    runs = ["jev-20261017-122314", "jev-20261018-110601", "jev-20261018-110607"]
    with connect() as conn:
        loaded = [load_run(conn, r) for r in runs]
    exp = loaded[0][1]["choice_base"]
    opts, truth = list(exp["options"]), loaded[0][3]
    hs = sorted(set.intersection(*[set(l[2]["choice_base"]) for l in loaded]))
    hs = [h for h in hs if h in truth and truth[h].product in opts]
    y = np.array([opts.index(truth[h].product) for h in hs])
    Ps = [np.array([choice_probs(l[2]["choice_base"][h], opts)[0] for h in hs]) for l in loaded]

    def score(P):
        correct = (P.argmax(axis=1) == y).astype(float)
        floor = P[P > 0].min() / 2 if (P == 0).any() else 0.0
        Pf = np.maximum(P, floor)
        P_cv, _ = M.crossfit_temperature(Pf / Pf.sum(axis=1, keepdims=True), y)
        return {"accuracy": float(correct.mean()), "ece_raw": M.ece(P.max(axis=1), correct, 15),
                "ece_calibrated": M.ece(P_cv.max(axis=1), (P_cv.argmax(axis=1) == y).astype(float), 15)}
    return {"rows": len(hs), "one run (mean of 3)": {k: float(np.mean([score(P)[k] for P in Ps])) for k in ("accuracy", "ece_raw", "ece_calibrated")},
            "two runs averaged (mean of 3 pairs)": {k: float(np.mean([score((Ps[i] + Ps[j]) / 2)[k] for i, j in ((0, 1), (0, 2), (1, 2))]))
                                                    for k in ("accuracy", "ece_raw", "ece_calibrated")},
            "three runs averaged": score(sum(Ps) / 3)}


def run():
    k8s, cfpb = load_check("check-k8s-sig"), load_check("check-cfpb-product")
    res = {
        "per_answer": {"k8s_sig": per_answer(k8s, 0.9), "cfpb_product": per_answer(cfpb, 0.8)},
        "optional_stopping": {"k8s_sig_90": optional_stopping(k8s, 0.9), "k8s_sig_95": optional_stopping(k8s, 0.95),
                              "cfpb_80": optional_stopping(cfpb, 0.8), "cfpb_85": optional_stopping(cfpb, 0.85)},
        "active_counts": active_counts(k8s, ["node", "api-machinery", "scheduling", "storage", "auth"]),
        "review_plan": {"k8s_sig_5": review_plan(k8s, 0.05), "k8s_sig_3": review_plan(k8s, 0.03),
                        "cfpb_10": review_plan(cfpb, 0.10), "cfpb_5": review_plan(cfpb, 0.05)},
        "ensembling_cfpb": ensembling(),
    }
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, "results.json"), "w") as f:
        json.dump(res, f, indent=2, default=float)
    with open(os.path.join(OUT, "report.md"), "w") as f:
        f.write(render(res))
    return OUT


def render(r):
    pct = lambda x: "–" if x is None else f"{100 * x:.1f} %"
    L = ["# Ideas from recent research, tested on stored answers", "",
         "No API calls. Generated by `jevbench frontier` from `results/check-k8s-sig`, `results/check-cfpb-product` "
         "(500 labelled judgments each) and three identical Phase 0 CFPB runs. Write-up: "
         "[docs/research/2026-10-frontier-review.md](../../docs/research/2026-10-frontier-review.md).", ""]
    L += ["## 1. Precision per answer under the overall guarantee", ""]
    for name, v in r["per_answer"].items():
        o = v["overall"]
        L += [f"**{name}**, overall target {pct(v['target'])}: threshold {o['threshold']:.3f}, {pct(o['auto_share'])} "
              f"auto-accepted at {pct(o['precision'])} precision. With a guarantee per answer instead: {pct(v['mondrian_auto_share'])}.", "",
              "| answer | answered | auto-accepted | precision | 95 % lower bound | own guarantee covers |",
              "| --- | ---: | ---: | ---: | ---: | ---: |"]
        L += [f"| {a['answer']} | {a['answered']} | {a['auto']} | {pct(a['precision'])} | {pct(a['lower'])} | "
              f"{pct(a['own_threshold_share'])} |" for a in v["answers"]]
        L.append("")
    L += ["## 2. Re-running `calibrate` as labels arrive", "",
          "Labels arrive 10 at a time (30 → 300, drawn with replacement). 1,000 trials. *Failure* = a threshold is "
          "deployed whose true precision is below the target; the guarantee says at most 5 % of trials.", "",
          "| population, target | policy | threshold found | failure (of all trials) | median auto share |",
          "| --- | --- | ---: | ---: | ---: |"]
    for name, v in r["optional_stopping"].items():
        for pol, x in v.items():
            if isinstance(x, dict):
                L.append(f"| {name} | {pol} | {pct(x['found'])} | {pct(x['failure_probability'])} | {pct(x['median_auto_share'])} |")
    L += ["", "## 3. Which rows to label for counts", "",
          "Horvitz–Thompson difference estimator, 95 % normal interval, 2,000 draws per cell; cells show coverage "
          "and mean interval width in rows. Population: the 500 Kubernetes issues.", "",
          "| answer (true count) | design | 50 labels | 100 labels | 150 labels |", "| --- | --- | --- | --- | --- |"]
    for c, v in r["active_counts"].items():
        for design, by in v["by_design"].items():
            cells = " | ".join(f"{pct(x['coverage'])} · ±{x['width_rows'] / 2:.0f}" for x in by.values())
            L.append(f"| {c} ({v['true_count']}) | {design} | {cells} |")
    L += ["", "## 4. Review planning with a guarantee", "",
          "Keep AI answers above a score, people review the rest; the cut is chosen so that the share of all rows "
          "left wrong is ≤ ε with 95 % confidence (one-sided Clopper–Pearson on random labels). 1,000 trials.", "",
          "| population | AI-only error | ε | review needed if every label were known | review with 100 labels | with 200 labels | failure (100 / 200) |",
          "| --- | ---: | ---: | ---: | ---: | ---: | ---: |"]
    for name, v in r["review_plan"].items():
        a, b = v["100"] if "100" in v else v[100], v["200"] if "200" in v else v[200]
        L.append(f"| {name.rsplit('_', 1)[0]} | {pct(v['ai_only_error'])} | {pct(v['eps'])} | {pct(v['oracle_review_share'])} | "
                 f"{pct(a['mean_review_share'])} | {pct(b['mean_review_share'])} | {pct(a['failure_rate'])} / {pct(b['failure_rate'])} |")
    e = r["ensembling_cfpb"]
    L += ["", "## 5. Asking more than once", "", f"{e['rows']:,} CFPB complaints, three identical runs (20 rows per request).", "",
          "| | accuracy | calibration error, raw | after calibration |", "| --- | ---: | ---: | ---: |"]
    for k in ("one run (mean of 3)", "two runs averaged (mean of 3 pairs)", "three runs averaged"):
        L.append(f"| {k} | {pct(e[k]['accuracy'])} | {e[k]['ece_raw']:.3f} | {e[k]['ece_calibrated']:.3f} |")
    return "\n".join(L) + "\n"
