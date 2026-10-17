"""jevbench: Phase 0 benchmark harness.

  fetch       download a CFPB complaint sample with narratives (CC0 mirror)
  load        load the sample into Postgres (bench.complaints, bench.items)
  run         run the experiments through pg-jev against a backend (mock | sim | jev | --api-url)
  analyze     write results/<run_id>/report.md and metrics.json
  cachecheck  show whether pg-jev reuses answers across backends within one session
"""
import argparse
import json
import sys

from . import fetch, report, runner
from .tasks import default_experiments


def main(argv=None):
    ap = argparse.ArgumentParser(prog="jevbench", description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    f = sub.add_parser("fetch")
    f.add_argument("--n", type=int, default=3000)
    f.add_argument("--out", default="data/raw/cfpb_sample.jsonl")
    f.add_argument("--seed", type=int, default=7)
    f.add_argument("--max-chars", type=int, default=1500)
    f.add_argument("--source", choices=["parquet", "api"], default="parquet")
    f.add_argument("--shards", default="0", help="parquet shards to sample from (0,1,2), comma-separated")

    l = sub.add_parser("load")
    l.add_argument("--input", default="data/raw/cfpb_sample.jsonl")
    l.add_argument("--n", type=int, default=2000)

    r = sub.add_parser("run")
    r.add_argument("--backend", default="sim", help="mock | sim | jev, or any name with --api-url")
    r.add_argument("--api-url", default=None, help="any /v1/systemone-compatible endpoint (stuntd, laya-server)")
    r.add_argument("--model", default=None)
    r.add_argument("--experiments", default="all", help="comma-separated names, or 'all'")
    r.add_argument("--max-usd", type=float, default=1.0, help="refuse paid runs estimated above this")
    r.add_argument("--yes", action="store_true", help="confirm a paid run")
    r.add_argument("--notes", default=None)
    r.add_argument("--analyze", action="store_true", help="write the report when the run finishes")

    a = sub.add_parser("analyze")
    a.add_argument("--run", default="latest")
    a.add_argument("--out", default="results")

    sub.add_parser("cachecheck")
    sub.add_parser("experiments")

    args = ap.parse_args(argv)
    if args.cmd == "fetch":
        if args.source == "parquet":
            shards = tuple(int(s) for s in args.shards.split(","))
            m = fetch.fetch_sample_parquet(args.n, args.out, seed=args.seed, max_chars=args.max_chars, shards=shards)
        else:
            m = fetch.fetch_sample_api(args.n, args.out, seed=args.seed, max_chars=args.max_chars)
        print(json.dumps(m, indent=2))
    elif args.cmd == "load":
        n, dist = runner.load_sample(args.input, args.n)
        print(f"loaded {n} complaints")
        for product, count in dist:
            print(f"  {count:>6}  {product}")
    elif args.cmd == "run":
        exps = default_experiments()
        if args.experiments != "all":
            wanted = set(args.experiments.split(","))
            exps = [e for e in exps if e.name in wanted]
            missing = wanted - {e.name for e in exps}
            if missing:
                sys.exit(f"unknown experiments: {sorted(missing)}")
        run_id = runner.run(args.backend, args.model, args.api_url, exps, args.max_usd, args.notes, args.yes)
        print(f"run_id: {run_id}")
        if args.analyze:
            out_dir, _ = report.analyse(run_id)
            print(f"report: {out_dir}/report.md")
    elif args.cmd == "analyze":
        out_dir, _ = report.analyse(args.run, args.out)
        print(f"report: {out_dir}/report.md")
    elif args.cmd == "cachecheck":
        print(json.dumps(runner.cache_check(), indent=2))
    elif args.cmd == "experiments":
        for e in default_experiments():
            print(f"{e.name:<24} {e.kind:<7} {e.notes or e.question}")


if __name__ == "__main__":
    main()
