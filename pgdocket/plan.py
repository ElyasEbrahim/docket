"""How much human review keeps a whole column's error at or below ε (issue #20).

People review the rows the model is least sure of and the AI keeps the rest. The cut is chosen so that, with
confidence 1 − α, at most ε of all judged rows are left wrong (probably approximately correct labels: Candès, Ilyas &
Zrnic, 2025). With a uniform random sample of labels, the share of rows that are kept *and* wrong is a proportion the
labels estimate without bias, so a one-sided Clopper–Pearson bound applies to each cut. That share only grows as the
cut is lowered, so testing cuts from the safest down and stopping at the first that fails needs no correction.
Assumes reviewers give the right answer, and that the labels were drawn at random from the judged rows.
"""
import csv
import math
import os

import numpy as np
from psycopg import sql

from . import metrics as M

LADDER = (0.10, 0.05, 0.03, 0.02, 0.01)


def labels_needed(eps, alpha=0.05):
    """Fewest random labels that could prove ε at all (when every kept labelled row is right)."""
    return math.ceil(math.log(alpha) / math.log(1 - eps))


def cut(conf, conf_lab, wrong_lab, eps, alpha=0.05):
    """The lowest confidence the AI may keep: rows below it go to people. None when even reviewing every row can't be
    shown to meet ε with these labels (too few). `conf`: every judged row; `*_lab`: the random labels."""
    conf, conf_lab, wrong_lab = np.asarray(conf, float), np.asarray(conf_lab, float), np.asarray(wrong_lab, float)
    n = len(conf_lab)
    upper = lambda k: 1 - M.clopper_pearson_lower(n - k, n, alpha)
    if n == 0 or upper(0) > eps:
        return None
    best = math.inf                                     # review everything
    for s in np.unique(conf)[::-1]:                     # keep more and more of the most confident rows
        if upper(int((wrong_lab * (conf_lab >= s)).sum())) > eps:
            break
        best = float(s)
    return best


def plan(conf, conf_lab, wrong_lab, eps, alpha=0.05, ladder=LADDER):
    conf = np.asarray(conf, float)
    n, N = len(conf_lab), len(conf)
    k_all = int(np.sum(wrong_lab))
    out = {"rows": N, "labels": n, "alpha": alpha,
           "ai_error": k_all / n if n else None,
           "ai_error_upper": 1 - M.clopper_pearson_lower(n - k_all, n, alpha) if n else None, "targets": []}
    for e in sorted(set(ladder) | {eps}, reverse=True):
        s = cut(conf, conf_lab, wrong_lab, e, alpha)
        review = int((conf < s).sum()) if s is not None else None
        out["targets"].append({"max_error": e, "cut": None if s is None or math.isinf(s) else s,
                               "review_all": s is not None and math.isinf(s), "review": review,
                               "review_share": review / N if review is not None and N else None,
                               "labels_needed": labels_needed(e, alpha), "requested": e == eps})
    return out


def fetch(conn, name):
    """Judged rows as the view shows them: key, answer, how sure the model is of that answer, random label if any."""
    d = conn.execute("SELECT d.id, v.spec FROM docket.decision d JOIN docket.version v ON v.decision_id = d.id "
                     "AND v.version = d.active_version WHERE d.name = %s", (name,)).fetchone()
    if not d:
        raise SystemExit(f"no decision named {name!r}")
    rows = conn.execute(sql.SQL(
        "SELECT v.key::text, v.answer, v.raw_score, l.label FROM docket.{} v "
        "LEFT JOIN docket.label l ON l.decision_id = %s AND l.row_key = v.key::text AND l.sampling = 'random' "
        "WHERE v.status = 'judged' ORDER BY v.raw_score, v.key").format(sql.Identifier("v_" + name)), (d[0],)).fetchall()
    noul = d[1]["kind"] == "noul"
    conf = lambda answer, p: (p if answer == "yes" else 1 - p) if noul else p     # how sure of the answer shown
    return {"decision_id": d[0], "spec": d[1],
            "rows": [{"key": k, "answer": a, "conf": conf(a, float(p)), "label": lab} for k, a, p, lab in rows]}


def from_rows(rows, eps, alpha=0.05):
    lab = [r for r in rows if r["label"] is not None]
    return plan([r["conf"] for r in rows], [r["conf"] for r in lab],
                [float(r["answer"] != r["label"]) for r in lab], eps, alpha)


def export_queue(conn, name, rows, s, path):
    """Write the rows people should review, least confident first, with their text: key, text, AI answer, label.
    Rows that already have a random label are left out (they're known)."""
    d = conn.execute("SELECT source, key_column, text_columns FROM docket.decision WHERE name = %s", (name,)).fetchone()
    todo = sorted((r for r in rows if r["conf"] < s and r["label"] is None), key=lambda r: (r["conf"], r["key"]))
    q = sql.SQL("SELECT {k}::text, {cols} FROM {t} WHERE {k}::text = ANY(%s)").format(
        k=sql.Identifier(d[1]), cols=sql.SQL(", ").join(sql.Identifier(c) for c in d[2]), t=sql.SQL(d[0]))
    text = {r[0]: r[1:] for r in conn.execute(q, ([r["key"] for r in todo],)).fetchall()}
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["key"] + list(d[2]) + ["ai_answer", "ai_confidence", "label"])
        for r in todo:
            w.writerow([r["key"]] + list(text.get(r["key"], [""] * len(d[2]))) + [r["answer"], f"{r['conf']:.3f}", ""])
    return len(todo)
