"""Fetch a GitHub repository's issues (not PRs) with their labels, as a real triage dataset.

Runs on the host and calls the GitHub CLI (`gh api`), so authentication stays with `gh` and no token is passed
around. Uses the search API month by month, which stays under its 1,000-results-per-query cap.

Issue text belongs to its authors: the output goes to data/raw/ (gitignored) and only aggregate results are committed.

  PYTHONPATH=harness python3 -m jevbench.ghissues --repo kubernetes/kubernetes --start 2024-07 --end 2026-06
"""
import argparse
import json
import os
import subprocess
import sys
import time
from datetime import date, datetime, timezone

MAX_BODY_CHARS = 2000


def _months(start, end):
    y, m = map(int, start.split("-"))
    ey, em = map(int, end.split("-"))
    while (y, m) <= (ey, em):
        first = date(y, m, 1)
        ny, nm = (y + 1, 1) if m == 12 else (y, m + 1)
        last = date.fromordinal(date(ny, nm, 1).toordinal() - 1)
        yield first.isoformat(), last.isoformat()
        y, m = ny, nm


def _search(query, page):
    cmd = ["gh", "api", "-X", "GET", "search/issues", "-f", f"q={query}", "-f", "per_page=100",
           "-f", f"page={page}", "-f", "sort=created", "-f", "order=asc"]
    for attempt in range(6):
        out = subprocess.run(cmd, capture_output=True, text=True)
        if out.returncode == 0:
            return json.loads(out.stdout)
        if "rate limit" in out.stderr.lower() or "403" in out.stderr or "429" in out.stderr:
            time.sleep(20 * (attempt + 1))
            continue
        raise RuntimeError(out.stderr.strip())
    raise RuntimeError("GitHub search rate limit: giving up")


def fetch(repo, start, end, out_path):
    rows, seen = [], set()
    for first, last in _months(start, end):
        query = f"repo:{repo} is:issue created:{first}..{last}"
        page, total = 1, None
        while True:
            data = _search(query, page)
            total = data["total_count"] if total is None else total
            if total > 1000:
                raise RuntimeError(f"{first}..{last}: {total} issues exceed the search cap; use smaller windows")
            for it in data["items"]:
                if it["number"] in seen or "pull_request" in it:
                    continue
                seen.add(it["number"])
                rows.append({
                    "number": it["number"], "created_at": it["created_at"], "closed_at": it.get("closed_at"),
                    "state": it["state"], "title": it["title"] or "",
                    "body": (it.get("body") or "")[:MAX_BODY_CHARS],
                    "labels": sorted(l["name"] for l in it.get("labels", [])),
                })
            if page * 100 >= total:
                break
            page += 1
            time.sleep(2.1)                       # search API: 30 requests per minute
        print(f"  {first[:7]}: {total} issues (running total {len(rows)})", flush=True)
        time.sleep(2.1)
    rows.sort(key=lambda r: r["created_at"])
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    with open(out_path, "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    manifest = {"repo": repo, "start": start, "end": end, "issues": len(rows), "max_body_chars": MAX_BODY_CHARS,
                "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "note": "Issue text belongs to its authors; keep raw data out of the repository."}
    with open(out_path + ".manifest.json", "w") as f:
        json.dump(manifest, f, indent=2)
    return manifest


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--repo", default="kubernetes/kubernetes")
    ap.add_argument("--start", default="2024-07", help="first month, YYYY-MM")
    ap.add_argument("--end", default="2026-06", help="last month, YYYY-MM")
    ap.add_argument("--out", default="data/raw/github_kubernetes.jsonl")
    a = ap.parse_args()
    print(json.dumps(fetch(a.repo, a.start, a.end, a.out), indent=2))


if __name__ == "__main__":
    sys.exit(main())
