"""Compare a shadow version of a decision with the active one, against the active one's own noise (issue #15).

On a sample of rows, three answers are available: the active version's live answer (old), the active version
re-asked as a probe (noise baseline), and the shadow version's answer (new).

- Changed answers: how often new differs from old, against how often old differs from itself when re-asked.
  Only the excess over that noise is caused by the change; it gets a paired bootstrap interval.
- Where answers move: the most common old → new transitions.
- Accuracy difference: where the two versions give the same answer, they are both right or both wrong, so only
  the rows where they disagree decide which is more accurate. Once every disagreement in the sample has a label
  (`--export-disagreements` lists them), the difference is known on every sampled row. Until then it is measured
  on random-sample labels only.
- A verdict: promote / keep current / no clear difference / needs labels.
"""
import csv
import json
import os
from collections import Counter
from datetime import datetime, timezone
from math import comb

import numpy as np
from psycopg import sql

from . import metrics as M
from .spec import option_names, read_answer

MIN_LABELS = 30


def decision_value(spec, answer):
    """The answer a reader would see: the option name (choice) or yes/no at 0.5 (yes/no)."""
    if answer is None:
        return None
    value, score = read_answer(spec, answer)
    return value if spec["kind"] == "choice" else ("yes" if score >= 0.5 else "no")


def analyse(spec_old, spec_new, rows, n_boot=2000, seed=0):
    """rows: dicts with old, probe, new (raw answers), label (or None) and sampling ('random', 'manual', 'all').
    Rows missing an answer are skipped."""
    rows = [r for r in rows if r["old"] is not None and r["probe"] is not None and r["new"] is not None]
    n = len(rows)
    if n == 0:
        return {"n": 0, "verdict": "incomplete", "reasons": ["no row has all three answers yet"]}
    old = [decision_value(spec_old, r["old"]) for r in rows]
    probe = [decision_value(spec_old, r["probe"]) for r in rows]
    new = [decision_value(spec_new, r["new"]) for r in rows]
    label = [r.get("label") for r in rows]
    changed_new = np.array([a != b for a, b in zip(old, new)], float)
    changed_noise = np.array([a != b for a, b in zip(old, probe)], float)
    diff = changed_new - changed_noise
    out = {
        "n": n,
        "changed": float(changed_new.mean()), "noise": float(changed_noise.mean()),
        "excess": float(diff.mean()), "excess_ci": M.bootstrap_ci(np.mean, [diff], n_boot=n_boot, seed=seed),
        "transitions": [{"old": a, "new": b, "rows": c}
                        for (a, b), c in Counter((a, b) for a, b in zip(old, new) if a != b).most_common(8)],
        "counts_old": dict(Counter(old).most_common()), "counts_new": dict(Counter(new).most_common()),
    }
    tok_old = [r["tokens_old"] for r in rows if r.get("tokens_old")]
    tok_new = [r["tokens_new"] for r in rows if r.get("tokens_new")]
    if tok_old and tok_new:
        out["tokens_per_row_old"], out["tokens_per_row_new"] = float(np.mean(tok_old)), float(np.mean(tok_new))

    right_old = np.array([o == l for o, l in zip(old, label)], float)
    right_new = np.array([nw == l for nw, l in zip(new, label)], float)
    has_label = np.array([l is not None for l in label])
    is_random = has_label & np.array([r.get("sampling", "random") == "random" for r in rows])
    disagree = changed_new.astype(bool)
    out["labels"] = int(is_random.sum())
    out["disagreements"], out["disagreements_labelled"] = int(disagree.sum()), int((disagree & has_label).sum())
    if out["disagreements_labelled"]:
        m = disagree & has_label
        out["disagreements_right"] = {"current": int((right_old[m] > right_new[m]).sum()),
                                      "new": int((right_new[m] > right_old[m]).sum()),
                                      "neither": int((right_old[m] + right_new[m] == 0).sum())}
        out["sign_test_p"] = sign_test(out["disagreements_right"]["current"], out["disagreements_right"]["new"])
    if is_random.any():
        out["accuracy_old"], out["accuracy_new"] = float(right_old[is_random].mean()), float(right_new[is_random].mean())
    if out["disagreements_labelled"] == out["disagreements"]:
        gain = np.where(disagree, right_new - right_old, 0.0)          # agreeing rows: both right or both wrong
        out["gain_from"] = "disagreements"
    elif out["labels"]:
        gain = (right_new - right_old)[is_random]
        out["gain_from"] = "random labels"
    if "gain_from" in out:
        out["accuracy_gain"] = float(gain.mean())
        out["accuracy_gain_ci"] = M.bootstrap_ci(np.mean, [gain], n_boot=n_boot, seed=seed)
    if spec_new["kind"] == "choice" and has_label.any():
        unknown = sum(1 for l in label if l is not None and l not in option_names(spec_new))
        if unknown:
            out["labels_not_options_of_new"] = unknown
    out.update(_verdict(out))
    return out


def sign_test(a, b):
    """Two-sided exact sign test: a wins against b wins, with ties (neither right) left out."""
    k = a + b
    return 1.0 if k == 0 else min(1.0, 2 * sum(comb(k, i) for i in range(min(a, b) + 1)) / 2 ** k)


def _verdict(r):
    pct = lambda x: f"{100 * x:.1f} %"
    pp = lambda x: f"{100 * x:+.1f} pp"
    reasons = []
    lo, hi = r["excess_ci"]
    if lo > 0:
        reasons.append(f"The new version changes {pct(r['changed'])} of answers, against {pct(r['noise'])} when the current "
                       f"one is simply asked again: {pct(r['excess'])} more [{pct(lo)}, {pct(hi)}] are due to the change.")
    else:
        reasons.append(f"The new version changes {pct(r['changed'])} of answers, against {pct(r['noise'])} when the current "
                       f"one is asked again: the difference [{pct(lo)}, {pct(hi)}] is within run-to-run noise.")
    gain_from = r.get("gain_from")
    if gain_from == "random labels" and r["labels"] < MIN_LABELS:
        gain_from = None
    if gain_from:
        glo, ghi = r["accuracy_gain_ci"]
        if gain_from == "disagreements" and not r["disagreements"]:
            basis = "The versions give the same answer on every row, so they are equally accurate here. "
        elif gain_from == "disagreements":
            w = r["disagreements_right"]
            basis = (f"The versions disagree on {r['disagreements']} of {r['n']} rows, all labelled: the current one was "
                     f"right on {w['current']}, the new one on {w['new']}, neither on {w['neither']} "
                     f"(exact sign test p = {r['sign_test_p']:.2f}). ")
        else:
            basis = f"On {r['labels']} random-sample labels: {pct(r['accuracy_old'])} → {pct(r['accuracy_new'])}. "
        acc = basis + f"Accuracy difference: {pp(r['accuracy_gain'])} [{pp(glo)}, {pp(ghi)}]."
        if glo > 0:
            verdict = "promote"
            reasons.append(acc + " The new version is more accurate.")
        elif ghi < 0:
            verdict = "keep current"
            reasons.append(acc + " The new version is less accurate.")
        else:
            verdict = "no clear difference"
            reasons.append(acc + f" No difference is detectable: the new version is between {100 * -glo:.1f} pp less "
                                 f"and {100 * ghi:.1f} pp more accurate.")
        if r.get("labels_not_options_of_new"):
            reasons.append(f"{r['labels_not_options_of_new']} labels are not options of the new version and count as wrong for it.")
    else:
        verdict = "needs labels"
        todo = r["disagreements"] - r["disagreements_labelled"]
        reasons.append(f"Which version is right can't be judged yet: {r['labels']} random-sample labels (need {MIN_LABELS}+), "
                       f"{r['disagreements_labelled']} of {r['disagreements']} disagreements labelled. Labelling the {todo} "
                       "rows where the versions disagree is enough (`--export-disagreements`).")
    if verdict == "no clear difference" and r.get("gain_from") == "random labels" and r["disagreements"]:
        todo = r["disagreements"] - r["disagreements_labelled"]
        reasons.append(f"To narrow this, label the {todo} rows where the versions disagree (`--export-disagreements`): "
                       f"that measures the difference on all {r['n']} rows.")
    if "tokens_per_row_new" in r:
        to, tn = r["tokens_per_row_old"], r["tokens_per_row_new"]
        cost = f"Tokens per row: {to:.0f} → {tn:.0f} ({100 * (tn / to - 1):+.0f} %)."
        if verdict == "no clear difference" and tn < to and r["accuracy_gain_ci"][0] < 0:
            cost += (f" Promote for the saving only if losing up to {100 * -r['accuracy_gain_ci'][0]:.1f} pp of accuracy "
                     "is acceptable.")
        reasons.append(cost)
    return {"verdict": verdict, "reasons": reasons}


# ---------------------------------------------------------------- database
def fetch(conn, name, version):
    d = conn.execute("SELECT id, active_version, source, key_column, text_columns FROM docket.decision WHERE name = %s",
                     (name,)).fetchone()
    if not d:
        raise SystemExit(f"no decision named {name!r}")
    did, active = d[0], d[1]
    specs = dict(conn.execute("SELECT version, spec FROM docket.version WHERE decision_id = %s AND version = ANY(%s)",
                              (did, [active, version])).fetchall())
    if version not in specs:
        raise SystemExit(f"{name} has no version {version}")
    rows = conn.execute("""
        WITH probe AS (
            SELECT DISTINCT ON (row_key) row_key, answer FROM docket.judgment
            WHERE decision_id = %(d)s AND version = %(a)s AND purpose = 'probe' ORDER BY row_key, id DESC)
        SELECT p.row_key, jo.answer, p.answer, jn.answer, l.label, l.sampling, jo.tokens, jn.tokens
        FROM probe p
        JOIN docket.current co ON co.decision_id = %(d)s AND co.version = %(a)s AND co.row_key = p.row_key
        JOIN docket.judgment jo ON jo.id = co.judgment_id
        LEFT JOIN docket.current cn ON cn.decision_id = %(d)s AND cn.version = %(v)s AND cn.row_key = p.row_key
        LEFT JOIN docket.judgment jn ON jn.id = cn.judgment_id
        LEFT JOIN docket.label l ON l.decision_id = %(d)s AND l.row_key = p.row_key
        ORDER BY p.row_key""", {"d": did, "a": active, "v": version}).fetchall()
    pending = conn.execute(
        "SELECT count(*) FROM docket.queue WHERE decision_id = %s AND attempts < 5 AND "
        "((version = %s AND purpose = 'live') OR (version = %s AND purpose = 'probe'))", (did, version, active)).fetchone()[0]
    cols = ("row_key", "old", "probe", "new", "label", "sampling", "tokens_old", "tokens_new")
    return {"decision_id": did, "active": active, "version": version, "spec_old": specs[active], "spec_new": specs[version],
            "source": d[2], "key": d[3], "text": d[4], "rows": [dict(zip(cols, r)) for r in rows], "pending": pending}


def export_disagreements(conn, data, path):
    """Write the compared rows where the versions disagree and no label exists yet: key, text, both answers, label."""
    so, sn = data["spec_old"], data["spec_new"]
    todo = {r["row_key"]: (decision_value(so, r["old"]), decision_value(sn, r["new"])) for r in data["rows"]
            if r["new"] is not None and r["label"] is None and decision_value(so, r["old"]) != decision_value(sn, r["new"])}
    q = sql.SQL("SELECT {k}::text, {cols} FROM {t} WHERE {k}::text = ANY(%s) ORDER BY {k}").format(
        k=sql.Identifier(data["key"]), cols=sql.SQL(", ").join(sql.Identifier(c) for c in data["text"]),
        t=sql.SQL(data["source"]))
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["key"] + list(data["text"]) + [f"v{data['active']}", f"v{data['version']}", "label"])
        for key, *text in conn.execute(q, (list(todo),)).fetchall():
            w.writerow([key] + text + list(todo[key]) + [""])
    return len(todo)


def store(conn, decision_id, version, result):
    conn.execute("UPDATE docket.version SET comparison = %s::jsonb WHERE decision_id = %s AND version = %s",
                 (json.dumps(result, default=float), decision_id, version))


def render(name, data, r):
    pct = lambda x: "–" if x is None else f"{100 * x:.1f} %"
    pp = lambda x: f"{100 * x:+.1f} pp"
    so, sn = data["spec_old"], data["spec_new"]
    L = [f"# Comparing `{name}` v{data['active']} (active) with v{data['version']} (shadow)", "",
         f"*{datetime.now(timezone.utc).isoformat(timespec='seconds')}* · {r['n']} rows compared", "",
         f"## Verdict: **{r['verdict']}**", ""]
    L += [f"- {x}" for x in r["reasons"]]
    L += ["", "## What changed in the spec", "", "| | v%s (active) | v%s (shadow) |" % (data["active"], data["version"]),
          "| --- | --- | --- |"]
    for key in ("question", "model", "backend", "batch_size"):
        if so.get(key) != sn.get(key):
            L.append(f"| {key} | {so.get(key)} | {sn.get(key)} |")
    L += [f"| {k} | {a} | {b} |" for k, a, b in _option_changes(so, sn)]
    L += ["", "## Answers that change", "", "| | share of rows |", "| --- | ---: |",
          f"| new version vs current | {pct(r['changed'])} |",
          f"| current asked again (noise) | {pct(r['noise'])} |",
          f"| due to the change | {pct(r['excess'])} [{pct(r['excess_ci'][0])}, {pct(r['excess_ci'][1])}] |", ""]
    if r["transitions"]:
        L += ["| current answer | new answer | rows |", "| --- | --- | ---: |"]
        L += [f"| {t['old']} | {t['new']} | {t['rows']} |" for t in r["transitions"]]
        L.append("")
    L += ["## Accuracy", "", "| | current | new | difference |", "| --- | ---: | ---: | ---: |"]
    if r.get("accuracy_old") is not None:
        L.append(f"| on {r['labels']} random-sample labels | {pct(r['accuracy_old'])} | {pct(r['accuracy_new'])} | "
                 f"{pp(r['accuracy_new'] - r['accuracy_old'])} |")
    if r.get("disagreements_right"):
        w = r["disagreements_right"]
        L.append(f"| right where they disagree ({r['disagreements_labelled']} of {r['disagreements']} labelled) | "
                 f"{w['current']} | {w['new']} | neither: {w['neither']} · sign test p = {r['sign_test_p']:.2f} |")
    if r.get("gain_from"):
        L.append(f"| **difference, 95 % interval** ({r['gain_from']}) | | | {pp(r['accuracy_gain'])} "
                 f"[{pp(r['accuracy_gain_ci'][0])}, {pp(r['accuracy_gain_ci'][1])}] |")
    L.append("")
    keys = sorted(set(r["counts_old"]) | set(r["counts_new"]), key=lambda k: -r["counts_old"].get(k, 0))
    L += ["## Answer counts in the sample", "", "| answer | current | new |", "| --- | ---: | ---: |"]
    L += [f"| {k} | {r['counts_old'].get(k, 0)} | {r['counts_new'].get(k, 0)} |" for k in keys]
    L += ["", "Intervals are 95 % paired bootstrap intervals over rows. \"Noise\" is the current version re-asked on "
          "the same rows (probe judgments), so only the excess over it is attributable to the change. Where both "
          "versions give the same answer they are equally right, so the accuracy difference depends only on the rows "
          "where they disagree."]
    return "\n".join(L) + "\n"


def _option_changes(so, sn):
    """Rows for the spec table: options added, removed or re-described, in a few words each."""
    a = {o["name"]: o.get("description") or "" for o in so.get("options", [])}
    b = {o["name"]: o.get("description") or "" for o in sn.get("options", [])}
    if a == b:
        return []
    described = lambda d: f"{len(d)} options, {sum(1 for v in d.values() if v)} with descriptions"
    out = [("options", described(a), described(b))]
    if set(a) - set(b) or set(b) - set(a):
        out.append(("names", ", ".join(sorted(set(a) - set(b))) or "–", ", ".join(sorted(set(b) - set(a))) or "–"))
    changed = sorted(k for k in set(a) & set(b) if a[k] != b[k])
    if changed and len(changed) <= 3:
        out += [(f"`{k}`", a[k] or "–", b[k] or "–") for k in changed]
    elif changed:
        out.append(("descriptions changed", f"{len(changed)} options", ", ".join(changed)))
    return out


def write(out_dir, md, result):
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "report.md"), "w") as f:
        f.write(md)
    with open(os.path.join(out_dir, "report.json"), "w") as f:
        json.dump(result, f, indent=2, default=float)
    return os.path.join(out_dir, "report.md")
