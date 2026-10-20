"""docket: durable, versioned, calibrated AI decisions for Postgres.

  docket check      how trustworthy is an AI decision on your table? (read-only)
  docket report     re-analyse a check folder from its saved answers (no API calls)

  docket install    create or upgrade the docket schema (no superuser needed)
  docket create     declare a decision on a table: triggers, queue, view docket.v_<name>
  docket worker     judge queued rows and keep the ledger current
  docket label      import human labels (from a column or a key,label CSV)
  docket calibrate  fit a calibrator and a guaranteed threshold from the labels
  docket status     decisions, queue depth, errors, labels, tokens
  docket drop       remove a decision (triggers, view, ledger); the source table is untouched
"""
import argparse
import json
import os
import sys

from .check import CheckConfig, export_sample, reanalyze, run_check


def _options(args):
    opts = []
    if args.options_file:
        with open(args.options_file) as f:
            data = json.load(f)
        opts = [o if isinstance(o, dict) else {"name": o} for o in data]
    elif args.options:
        opts = [{"name": o.strip()} for o in args.options.split(",") if o.strip()]
    return opts


def main(argv=None):
    ap = argparse.ArgumentParser(prog="docket", description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("check", help="sample, judge and score an AI decision against labels (read-only)")
    c.add_argument("--dsn", default=os.environ.get("DATABASE_URL"), help="Postgres connection string (or DATABASE_URL)")
    c.add_argument("--table", required=True, help="schema.table")
    c.add_argument("--key", required=True, help="primary-key column")
    c.add_argument("--text", required=True, help="comma-separated columns sent to the model")
    c.add_argument("--kind", choices=["choice", "noul"], required=True, help="choice: pick one option; noul: yes/no")
    c.add_argument("--question", required=True, help="choice: the question; noul: the condition to test")
    c.add_argument("--options", help="choice: comma-separated option names (must match the label values)")
    c.add_argument("--options-file", help='choice: JSON list of {"name", "description"}')
    lab = c.add_mutually_exclusive_group()
    lab.add_argument("--label-column", help="column holding existing human labels")
    lab.add_argument("--label-file", help="CSV with key,label (see --export-sample)")
    c.add_argument("--positive", help="noul: the label value that means yes")
    c.add_argument("--where", help="extra SQL filter on the table, e.g. \"created_at > '2025-01-01'\"")
    c.add_argument("--sample", type=int, default=300)
    c.add_argument("--seed", default="1")
    c.add_argument("--backend", default="jev", help="jev | sim | any /v1/systemone URL")
    c.add_argument("--model", default="jev-1.13.0")
    c.add_argument("--batch-size", type=int, default=1)
    c.add_argument("--repeat", type=int, default=0, help="re-judge this many rows to measure stability")
    c.add_argument("--batch-test", type=int, default=0, help="re-judge this many rows 20 per request")
    c.add_argument("--precision-target", type=float, default=0.9)
    c.add_argument("--max-usd", type=float, default=1.0)
    c.add_argument("--yes", action="store_true", help="confirm a paid run")
    c.add_argument("--out", help="output folder (default results/check-<timestamp>)")
    c.add_argument("--export-sample", metavar="CSV", help="only write the sample (with an empty label column) and exit")
    def dsn_arg(p):
        p.add_argument("--dsn", default=os.environ.get("DATABASE_URL"), help="Postgres connection string (or DATABASE_URL)")

    i = sub.add_parser("install", help="create or upgrade the docket schema")
    dsn_arg(i)
    cr = sub.add_parser("create", help="declare a decision on a table")
    dsn_arg(cr)
    cr.add_argument("name")
    cr.add_argument("--table", required=True)
    cr.add_argument("--key", required=True)
    cr.add_argument("--text", required=True, help="comma-separated columns sent to the model")
    cr.add_argument("--kind", choices=["choice", "noul"], required=True)
    cr.add_argument("--question", required=True)
    cr.add_argument("--options")
    cr.add_argument("--options-file")
    cr.add_argument("--backend", default="jev")
    cr.add_argument("--model", default="jev-1.13.0")
    cr.add_argument("--batch-size", type=int, default=1)
    cr.add_argument("--no-backfill", action="store_true", help="only judge rows inserted or changed from now on")
    w = sub.add_parser("worker", help="judge queued rows")
    dsn_arg(w)
    w.add_argument("--once", action="store_true", help="exit when the queue is empty")
    w.add_argument("--max-usd", type=float, default=None, help="stop after spending this much")
    w.add_argument("--claim-size", type=int, default=100)
    w.add_argument("--concurrency", type=int, default=16)
    w.add_argument("--poll", type=float, default=5.0, help="seconds between polls when idle")
    lb = sub.add_parser("label", help="import human labels")
    dsn_arg(lb)
    lb.add_argument("name")
    src = lb.add_mutually_exclusive_group(required=True)
    src.add_argument("--from-column")
    src.add_argument("--csv")
    lb.add_argument("--sample", type=int, default=None, help="with --from-column: a random sample of this many rows")
    lb.add_argument("--seed", default="1")
    ca = sub.add_parser("calibrate", help="fit a calibrator and a guaranteed threshold")
    dsn_arg(ca)
    ca.add_argument("name")
    ca.add_argument("--precision-target", type=float, default=0.9)
    ca.add_argument("--positive", default="true", help="noul: the label value that means yes")
    st = sub.add_parser("status", help="decisions, queue, errors, labels, tokens")
    dsn_arg(st)
    dr = sub.add_parser("drop", help="remove a decision and its ledger")
    dsn_arg(dr)
    dr.add_argument("name")
    dr.add_argument("--yes", action="store_true", help="confirm: this deletes the decision's ledger")

    r = sub.add_parser("report", help="re-analyse a check folder from its saved answers (no API calls)")
    r.add_argument("folder")
    r.add_argument("--precision-target", type=float, default=None)
    a = ap.parse_args(argv)

    if a.cmd == "report":
        reanalyze(a.folder, a.precision_target)
        print(f"report: {a.folder}/report.md")
        return
    if a.cmd in ("install", "create", "worker", "label", "calibrate", "status", "drop"):
        if not a.dsn:
            sys.exit("no database: pass --dsn or set DATABASE_URL")
        return _ledger_command(a)
    if not a.dsn:
        sys.exit("no database: pass --dsn or set DATABASE_URL")
    cfg = CheckConfig(dsn=a.dsn, table=a.table, key=a.key, text=[t.strip() for t in a.text.split(",")], kind=a.kind,
                      question=a.question, options=_options(a), label_column=a.label_column, label_file=a.label_file,
                      positive=a.positive, where=a.where, sample=a.sample, seed=a.seed, backend=a.backend,
                      model=a.model, batch_size=a.batch_size, repeat=a.repeat, batch_test=a.batch_test,
                      precision_target=a.precision_target, max_usd=a.max_usd, out=a.out)
    if a.export_sample:
        n = export_sample(cfg, a.export_sample)
        print(f"wrote {n} rows to {a.export_sample}; fill in the label column, then run with --label-file")
        return
    if a.kind == "choice" and not cfg.options:
        sys.exit("choice needs --options or --options-file")
    if a.kind == "noul" and not a.positive:
        sys.exit("noul needs --positive (the label value that means yes)")
    if not (a.label_column or a.label_file):
        sys.exit("needs labels: --label-column, or --label-file (create one with --export-sample)")
    out, _ = run_check(cfg, api_key=os.environ.get("TYPESAFE_API_KEY") or None, yes=a.yes)
    print(f"report: {out}/report.md")


def _ledger_command(a):
    from . import ledger
    if a.cmd == "install":
        applied = ledger.install(a.dsn)
        print("applied: " + (", ".join(applied) if applied else "nothing (already up to date)"))
    elif a.cmd == "create":
        spec = ledger.load_spec(a.kind, a.question, a.options, a.options_file, a.backend, a.model, a.batch_size)
        did, queued = ledger.create(a.dsn, a.name, a.table, a.key, [t.strip() for t in a.text.split(",")], spec,
                                    backfill=not a.no_backfill)
        print(f"decision {a.name} (id {did}) created; {queued} rows queued; read it from docket.v_{a.name}")
    elif a.cmd == "worker":
        from .worker import Worker
        totals = Worker(a.dsn, api_key=os.environ.get("TYPESAFE_API_KEY") or None, claim_size=a.claim_size,
                        concurrency=a.concurrency, max_usd=a.max_usd, poll=a.poll).run(once=a.once)
        print(json.dumps(totals))
    elif a.cmd == "label":
        n = ledger.import_labels(a.dsn, a.name, column=a.from_column, csv_path=a.csv, sample=a.sample, seed=a.seed)
        print(f"{n} labels imported for {a.name}")
    elif a.cmd == "calibrate":
        cal = ledger.calibrate(a.dsn, a.name, a.precision_target, positive=a.positive)
        thr = (f"auto-accept at ≥ {cal['threshold']:.3f}: {100 * cal['coverage']:.1f} % of rows with precision "
               f"≥ {100 * cal['precision_target']:.0f} % (95 % confidence)" if cal["threshold"] is not None
               else f"no threshold reaches {100 * cal['precision_target']:.0f} % precision with {cal['n_labels']} labels")
        print(f"{a.name}: {cal['n_labels']} labels · calibration error {cal['ece_raw']:.3f} → {cal['ece_calibrated']:.3f} · {thr}")
    elif a.cmd == "drop":
        if not a.yes:
            sys.exit(f"this deletes decision {a.name} and its whole ledger; re-run with --yes")
        with ledger.connect(a.dsn) as conn:
            conn.execute("SELECT docket.drop_decision(%s)", (a.name,))
        print(f"decision {a.name} dropped")
    elif a.cmd == "status":
        rows = ledger.status(a.dsn)
        if not rows:
            print("no decisions yet")
        for r in rows:
            print(f"{r['name']:<24} v{r['version']}  judged {r['judged']:>8,}  queued {r['queued']:>6,}  errors {r['errors']:>4,}  "
                  f"labels {r['labels']:>5,}  tokens {r['tokens']:>12,}  {'calibrated' if r['calibrated'] else 'not calibrated'}")


if __name__ == "__main__":
    main()
