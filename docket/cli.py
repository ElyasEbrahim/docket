"""docket: durable, versioned, calibrated AI decisions for Postgres.

  docket check   how trustworthy is an AI decision on your table? (read-only)
  docket report  re-analyse a check folder from its saved answers (no API calls)
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
    r = sub.add_parser("report", help="re-analyse a check folder from its saved answers (no API calls)")
    r.add_argument("folder")
    r.add_argument("--precision-target", type=float, default=None)
    a = ap.parse_args(argv)

    if a.cmd == "report":
        reanalyze(a.folder, a.precision_target)
        print(f"report: {a.folder}/report.md")
        return
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


if __name__ == "__main__":
    main()
