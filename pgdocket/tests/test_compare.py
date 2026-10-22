"""Version comparison (issue #15): changed answers against the noise baseline, accuracy, and the verdict."""
import numpy as np

from pgdocket import compare

OPTS = ["billing", "technical", "sales"]
SPEC = {"kind": "choice", "question": "Which team?", "options": [{"name": o} for o in OPTS], "model": "m", "backend": "b"}
YESNO = {"kind": "noul", "question": "Is it urgent?", "model": "m", "backend": "b"}


def _ans(pick):
    return {"choice": pick, "probabilities": {o: (0.8 if o == pick else 0.1) for o in OPTS}}


def _rows(truth, old, probe, new, labelled):
    return [{"old": _ans(o), "probe": _ans(p), "new": _ans(n), "label": t if i < labelled else None}
            for i, (t, o, p, n) in enumerate(zip(truth, old, probe, new))]


def _other(x, rng):
    return rng.choice([o for o in OPTS if o != x])


def test_a_better_version_is_promoted_and_its_changes_exceed_noise():
    rng = np.random.default_rng(0)
    truth = [OPTS[i % 3] for i in range(200)]
    old = [t if rng.random() < 0.7 else _other(t, rng) for t in truth]
    probe = [o if rng.random() < 0.97 else _other(o, rng) for o in old]
    new = [t if rng.random() < 0.9 else _other(t, rng) for t in truth]
    r = compare.analyse(SPEC, SPEC, _rows(truth, old, probe, new, labelled=120), n_boot=500)
    assert r["n"] == 200 and r["labels"] == 120
    assert r["excess_ci"][0] > 0 and r["changed"] > r["noise"]
    assert r["accuracy_gain_ci"][0] > 0
    assert r["verdict"] == "promote"
    assert sum(t["rows"] for t in r["transitions"]) <= r["changed"] * r["n"]


def test_changes_no_larger_than_noise_are_reported_as_noise():
    rng = np.random.default_rng(1)
    truth = [OPTS[i % 3] for i in range(150)]
    old = [t if rng.random() < 0.8 else _other(t, rng) for t in truth]
    probe = [o if rng.random() < 0.95 else _other(o, rng) for o in old]
    new = [o if rng.random() < 0.95 else _other(o, rng) for o in old]      # same model, re-asked
    r = compare.analyse(SPEC, SPEC, _rows(truth, old, probe, new, labelled=0), n_boot=500)
    assert r["excess_ci"][0] <= 0 <= r["excess_ci"][1]
    assert "within run-to-run noise" in r["reasons"][0]
    assert r["verdict"] == "needs labels"


def test_worse_version_and_labels_that_are_not_new_options():
    v2 = {**SPEC, "options": [{"name": "billing"}, {"name": "engineering"}, {"name": "sales"}]}
    truth = [OPTS[i % 3] for i in range(90)]
    rows = [{"old": _ans(t), "probe": _ans(t), "label": t,
             "new": {"choice": "billing" if t == "technical" else t,
                     "probabilities": {"billing": 0.8, "engineering": 0.1, "sales": 0.1} if t != "sales"
                     else {"billing": 0.1, "engineering": 0.1, "sales": 0.8}}} for t in truth]
    r = compare.analyse(SPEC, v2, rows, n_boot=500)
    assert r["noise"] == 0 and abs(r["changed"] - 1 / 3) < 1e-9
    assert r["transitions"] == [{"old": "technical", "new": "billing", "rows": 30}]
    assert r["labels_not_options_of_new"] == 30
    assert r["verdict"] == "keep current"


def test_yes_no_compares_decisions_at_one_half_and_skips_unfinished_rows():
    rows = [{"old": {"noul": 0.7}, "probe": {"noul": 0.6}, "new": {"noul": 0.4}, "label": None},
            {"old": {"noul": 0.2}, "probe": {"noul": 0.3}, "new": {"noul": 0.1}, "label": None},
            {"old": {"noul": 0.2}, "probe": {"noul": 0.3}, "new": None, "label": None}]
    r = compare.analyse(YESNO, YESNO, rows, n_boot=200)
    assert r["n"] == 2 and r["changed"] == 0.5 and r["noise"] == 0
    assert r["counts_old"] == {"yes": 1, "no": 1} and r["counts_new"] == {"no": 2}
    assert compare.analyse(YESNO, YESNO, rows[2:])["verdict"] == "incomplete"


def test_excess_interval_covers_the_true_excess_95_percent_of_the_time():
    """The paired bootstrap interval on (changed - noise) at the sample sizes `compare` is used with."""
    rng = np.random.default_rng(7)
    n, trials, hits = 150, 300, 0
    p_new, p_noise = 0.12, 0.04                    # true change rates; the noise flips are independent of the new ones
    for _ in range(trials):
        d = (rng.random(n) < p_new).astype(float) - (rng.random(n) < p_noise).astype(float)
        lo, hi = compare.M.bootstrap_ci(np.mean, [d], n_boot=400, seed=int(rng.integers(1 << 30)))
        hits += lo <= p_new - p_noise <= hi
    assert hits / trials >= 0.92


def test_render_names_what_changed_in_the_spec():
    v2 = {**SPEC, "model": "m2"}
    truth = [OPTS[i % 3] for i in range(40)]
    r = compare.analyse(SPEC, v2, _rows(truth, truth, truth, truth, labelled=40), n_boot=200)
    md = compare.render("triage", {"active": 1, "version": 2, "spec_old": SPEC, "spec_new": v2}, r)
    assert "| model | m | m2 |" in md and "Verdict: **no clear difference**" in md


def test_labels_on_the_disagreements_alone_give_the_full_label_answer():
    """Where both versions answer the same they are equally right, so labelling only the disagreements is enough."""
    rng = np.random.default_rng(3)
    truth = [OPTS[i % 3] for i in range(300)]
    old = [t if rng.random() < 0.9 else _other(t, rng) for t in truth]
    new = [o if rng.random() < 0.94 else (t if rng.random() < 0.3 else _other(o, rng)) for o, t in zip(old, truth)]
    full = _rows(truth, old, old, new, labelled=300)
    only = [r | {"label": r["label"] if o != n else None, "sampling": "manual"} for r, o, n in zip(full, old, new)]
    a, b = compare.analyse(SPEC, SPEC, full, n_boot=500), compare.analyse(SPEC, SPEC, only, n_boot=500)
    assert b["gain_from"] == "disagreements" and b["labels"] == 0 and b["disagreements_labelled"] == b["disagreements"] > 0
    assert b["accuracy_gain"] == a["accuracy_gain"] and b["accuracy_gain_ci"] == a["accuracy_gain_ci"]
    assert b["verdict"] == a["verdict"] and "accuracy_old" not in b


def test_some_disagreements_unlabelled_falls_back_to_random_labels_and_says_what_to_label():
    rng = np.random.default_rng(4)
    truth = [OPTS[i % 3] for i in range(200)]
    old = [t if rng.random() < 0.85 else _other(t, rng) for t in truth]
    new = [o if rng.random() < 0.9 else _other(o, rng) for o in old]
    r = compare.analyse(SPEC, SPEC, _rows(truth, old, old, new, labelled=60), n_boot=500)
    assert r["gain_from"] == "random labels" and r["disagreements_labelled"] < r["disagreements"]
    if r["verdict"] == "no clear difference":
        assert any("--export-disagreements" in x for x in r["reasons"])


def test_sign_test_matches_the_binomial_distribution():
    assert compare.sign_test(8, 2) == 2 * (1 + 10 + 45) / 1024
    assert compare.sign_test(0, 0) == 1.0 and compare.sign_test(5, 5) == 1.0
    assert compare.sign_test(0, 6) == 2 / 64


def _conf(pick, p):
    return {"choice": pick, "probabilities": {o: (p if o == pick else (1 - p) / 2) for o in OPTS}}


def test_calibration_compares_how_many_rows_each_version_could_auto_accept():
    """Same accuracy, but only the new version's confidence separates right from wrong: it can auto-accept more."""
    rng = np.random.default_rng(5)
    truth = [OPTS[i % 3] for i in range(240)]
    picks = [t if rng.random() < 0.85 else _other(t, rng) for t in truth]
    rows = [{"old": _conf(p, 0.7), "probe": _conf(p, 0.7), "label": t if i < 160 else None,
             "new": _conf(p, 0.97 if p == t else 0.5)} for i, (t, p) in enumerate(zip(truth, picks))]
    r = compare.analyse(SPEC, SPEC, rows, n_boot=200, precision_target=0.9)
    cur, new = r["calibration"]["current"], r["calibration"]["new"]
    assert cur["n_labels"] == new["n_labels"] == 160 and cur["precision_target"] == 0.9
    assert cur["auto_share"] is None                       # flat confidence at 85 % accuracy: nothing reaches 90 %
    assert new["auto_share"] > 0.7 and new["ece_calibrated"] < 0.1
    assert any("Auto-accept at ≥ 90 % precision" in x for x in r["reasons"])
    md = compare.render("t", {"active": 1, "version": 2, "spec_old": SPEC, "spec_new": SPEC}, r)
    assert "## Calibration on the same 160 random labels" in md


def test_no_calibration_comparison_with_too_few_random_labels():
    truth = [OPTS[i % 3] for i in range(60)]
    r = compare.analyse(SPEC, SPEC, _rows(truth, truth, truth, truth, labelled=20), n_boot=100)
    assert "calibration" not in r


def test_labels_of_a_removed_option_count_as_wrong_for_the_threshold():
    """A version without `technical` can't be right on technical rows; dropping those labels would inflate precision."""
    from pgdocket import calibration
    v2 = {**SPEC, "options": [{"name": "billing"}, {"name": "sales"}]}
    two = lambda pick: {"choice": pick, "probabilities": {o: (0.95 if o == pick else 0.05) for o in ("billing", "sales")}}
    labels = ["billing", "sales", "technical"] * 40
    answers = [two("billing" if l == "technical" else l) for l in labels]
    cal = calibration.fit(v2, answers, labels, precision_target=0.9)
    assert cal["labels_not_options"] == 40 and cal["n_labels"] == 120
    assert abs(cal["accuracy"] - 2 / 3) < 1e-9 and cal["threshold"] is None    # true precision 67 %: no guarantee
    kept = [i for i, l in enumerate(labels) if l != "technical"]
    assert calibration.fit(v2, [answers[i] for i in kept], [labels[i] for i in kept], 0.9)["threshold"] is not None
