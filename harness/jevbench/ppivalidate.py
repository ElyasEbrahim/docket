"""Do PPI intervals hold on a real model's real mistakes? (no API calls)

Takes answers already stored by `pgdocket check` for rows whose true label is known, treats those rows as the
whole population, and repeatedly draws a random sample of n labels. For every draw and every answer it computes
the PPI++ interval and the labels-only interval for the number of rows with that answer, and records how often
each contains the true number, and how wide it is.
"""
import json
import os

import numpy as np

from pgdocket.estimate import ppi_share
from pgdocket.spec import option_display, option_names, read_answer


def load(judgments, kind, options=None, positive=None):
    spec = {"kind": kind, "question": "", "options": options or []}
    rows = [json.loads(line) for line in open(judgments)]
    if kind == "choice":
        names = option_names(spec)
        answers = [read_answer(spec, r["answer"])[0] for r in rows]
        labels = [r["label"] for r in rows]
        return names, answers, labels
    answers = ["yes" if float(r["answer"]["noul"]) >= 0.5 else "no" for r in rows]
    labels = ["yes" if r["label"] == positive else "no" for r in rows]
    return ["yes"], answers, labels


def validate(names, answers, labels, sizes=(50, 100, 150), draws=2000, level=0.95, seed=0):
    rng = np.random.default_rng(seed)
    N = len(labels)
    out = {"population": N, "level": level, "draws": draws, "answers": {}}
    for c in names:
        f = np.array([a == c for a in answers], float)
        y = np.array([l == c for l in labels], float)
        truth = int(y.sum())
        res = {"true_count": truth, "model_count": int(f.sum()), "by_n": {}}
        for n in sizes:
            ppi_hit = lab_hit = abstain = 0
            ppi_w, lab_w, reliable, rel_hit = [], [], 0, 0
            for _ in range(draws):
                idx = rng.choice(N, n, replace=False)
                m = np.zeros(N, bool)
                m[idx] = True
                r = ppi_share(f[~m], f[m], y[m], level)
                if r["estimate"] is None:                 # no labelled example on one side: no interval given
                    abstain += 1
                    continue
                lo, hi = r["ci_low"] * N, r["ci_high"] * N
                llo, lhi = r["labels_low"] * N, r["labels_high"] * N
                hit = lo <= truth <= hi
                ppi_hit += hit
                lab_hit += llo <= truth <= lhi
                ppi_w.append(hi - lo)
                lab_w.append(lhi - llo)
                if r["reliable"]:
                    reliable += 1
                    rel_hit += hit
            given = draws - abstain
            res["by_n"][n] = {"coverage_ppi": ppi_hit / given if given else None,
                              "coverage_labels_only": lab_hit / given if given else None, "no_interval": abstain / draws,
                              "width_ppi": float(np.mean(ppi_w)) if ppi_w else float("nan"),
                              "width_labels_only": float(np.mean(lab_w)) if lab_w else float("nan"),
                              "share_reliable": reliable / draws,
                              "coverage_when_reliable": (rel_hit / reliable) if reliable else None}
        out["answers"][c] = res
    return out


def render(title, v):
    L = [f"## {title}", "", f"Population: {v['population']} rows with known true labels · {v['draws']} random label draws "
         f"per sample size · {100 * v['level']:.0f} % intervals.", "",
         "Coverage and widths are over draws that gave an interval; *no interval* = draws with no labelled example "
         "with (or without) the answer, where nothing is claimed.", "",
         "| answer | true count | model's count | labels | PPI covers truth | labels-only covers | PPI width | labels-only width | no interval | reliable draws | PPI covers when reliable |",
         "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |"]
    for c, r in v["answers"].items():
        for n, b in r["by_n"].items():
            cw = "–" if b["coverage_when_reliable"] is None else f"{100 * b['coverage_when_reliable']:.1f} %"
            pc = lambda x: "–" if x is None else f"{100 * x:.1f} %"
            L.append(f"| {c} | {r['true_count']} | {r['model_count']} | {n} | {pc(b['coverage_ppi'])} | "
                     f"{pc(b['coverage_labels_only'])} | ±{b['width_ppi'] / 2:.1f} | ±{b['width_labels_only'] / 2:.1f} | "
                     f"{100 * b['no_interval']:.0f} % | {100 * b['share_reliable']:.0f} % | {cw} |")
    return "\n".join(L) + "\n"


def run(out_dir="results/ppi-validation"):
    sig_opts = json.load(open("examples/k8s_sig_options.json"))
    sig = validate(*load("results/check-k8s-sig/judgments.jsonl", "choice", options=sig_opts))
    feat = validate(*load("results/check-k8s-feature/judgments.jsonl", "noul", positive="feature"))
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "validation.json"), "w") as f:
        json.dump({"k8s_sig": sig, "k8s_feature": feat}, f, indent=2)
    md = ("# Do PPI intervals hold on real model errors?\n\n"
          "Answers from jev-1.13.0 stored by `pgdocket check` (results/check-k8s-sig, results/check-k8s-feature); "
          "true labels are the SIG and kind labels people applied. No API calls. Generated by `jevbench ppivalidate`.\n\n"
          + render("Kubernetes issues: which SIG (10 options)", sig) + "\n"
          + render("Kubernetes issues: is it a feature request?", feat))
    with open(os.path.join(out_dir, "report.md"), "w") as f:
        f.write(md)
    return out_dir
