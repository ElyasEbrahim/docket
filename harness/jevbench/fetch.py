"""Fetch a random sample of CFPB complaints with narratives.

CFPB stopped publishing consumer narratives on 14 Aug 2026 (the live API and bulk CSV no longer carry them).
Narratives published before that were CC0; this uses the CC0 Hugging Face mirror
BEE-spoke-data/consumer-finance-complaints (config `has-text`, 1.69M complaints, 2015-03 → 2024-02)
through the Hugging Face hub.

Two sources:
  parquet (default)  download whole parquet shard(s) (~300 MB each, cached in data/raw/hf) and keep each row with
                     equal probability: a uniform sample of the shard
  api                datasets-server rows API, random offsets × runs of 20 rows; no download, but the anonymous
                     rate limit makes it slow and flaky (set HF_TOKEN)
Rows are filtered to products that map cleanly onto the benchmark label set and de-duplicated by narrative text.
"""
import hashlib
import json
import os
import random
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

from .tasks import PRODUCT_MAP

DATASET = "BEE-spoke-data/consumer-finance-complaints"
CONFIG = "has-text"
SPLIT = "train"
ROWS_API = "https://datasets-server.huggingface.co/rows"
SIZE_API = "https://datasets-server.huggingface.co/size"
INFO_API = "https://huggingface.co/api/datasets/" + DATASET


def _get_json(url, tries=10):
    headers = {"User-Agent": "docket-phase0-harness/0.1"}
    token = os.environ.get("HF_TOKEN")
    if token:
        headers["Authorization"] = "Bearer " + token
    delay = 2.0
    for attempt in range(tries):
        wait = None
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=60) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code not in (429, 500, 502, 503, 504) or attempt == tries - 1:
                raise
            ra = e.headers.get("Retry-After")
            wait = float(ra) if ra and ra.replace(".", "", 1).isdigit() else None
        except (urllib.error.URLError, TimeoutError):
            if attempt == tries - 1:
                raise
        time.sleep(min(wait if wait is not None else delay, 120) + random.random())
        delay = min(delay * 2, 60)


def dataset_info():
    info = _get_json(INFO_API)
    size = _get_json(SIZE_API + "?" + urllib.parse.urlencode({"dataset": DATASET}))
    n = next(c["num_rows"] for c in size["size"]["configs"] if c["config"] == CONFIG)
    return {"sha": info.get("sha"), "license": (info.get("cardData") or {}).get("license"), "num_rows": n}


def _rows(offset, length):
    q = urllib.parse.urlencode({"dataset": DATASET, "config": CONFIG, "split": SPLIT,
                                "offset": offset, "length": length})
    return [r["row"] for r in _get_json(ROWS_API + "?" + q)["rows"]]


def normalise(row, max_chars):
    product = PRODUCT_MAP.get(row.get("Product") or "")
    text = (row.get("Consumer complaint narrative") or "").strip()
    if not product or len(text) < 40:
        return None
    text = text[:max_chars]
    return {
        "complaint_id": str(row.get("Complaint ID")),
        "date_received": (row.get("Date received") or "")[:10] or None,
        "product_raw": row.get("Product"),
        "product": product,
        "issue": row.get("Issue"),
        "sub_issue": None if row.get("Sub-issue") in (None, "None") else row.get("Sub-issue"),
        "narrative": text,
        "text_hash": hashlib.md5(text.encode("utf-8")).hexdigest(),
    }


SHARD_URL = ("https://huggingface.co/datasets/" + DATASET +
             "/resolve/{rev}/has-text/train-{i:05d}-of-00003.parquet")
SHARD_COLUMNS = ["Date received", "Product", "Sub-product", "Issue", "Sub-issue",
                 "Consumer complaint narrative", "Complaint ID"]


def _download(url, path):
    if os.path.exists(path) and os.path.getsize(path) > 0:
        return path
    tmp = path + ".part"
    with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "docket-phase0-harness/0.1"}),
                                timeout=120) as r, open(tmp, "wb") as f:
        while chunk := r.read(1 << 20):
            f.write(chunk)
    os.replace(tmp, path)
    return path


def fetch_sample_parquet(n, out_path, seed=7, max_chars=1500, shards=(0,), cache_dir="data/raw/hf"):
    """Sample uniformly from whole parquet shards (robust to the rows API's anonymous rate limit)."""
    import pyarrow.parquet as pq

    info = dataset_info()
    rng = random.Random(seed)
    os.makedirs(cache_dir, exist_ok=True)
    files = []
    for i in shards:
        path = os.path.join(cache_dir, f"train-{i:05d}-of-00003.parquet")
        files.append(_download(SHARD_URL.format(rev=info["sha"] or "main", i=i), path))
    total = sum(pq.ParquetFile(f).metadata.num_rows for f in files)
    p_keep = min(1.0, n * 1.5 / total)                   # over-sample: unmapped products, duplicates
    seen, out = set(), []
    for f in files:
        pf = pq.ParquetFile(f)
        for g in range(pf.num_row_groups):
            table = pf.read_row_group(g, columns=SHARD_COLUMNS)
            for row in table.to_pylist():
                if rng.random() >= p_keep:
                    continue
                r = normalise(row, max_chars)
                if r and r["text_hash"] not in seen and r["complaint_id"] not in seen:
                    seen.update((r["text_hash"], r["complaint_id"]))
                    out.append(r)
    rng.shuffle(out)
    out = out[:n]
    return _write(out, out_path, {
        "dataset": DATASET, "config": CONFIG, "split": SPLIT, "revision": info["sha"], "license": info["license"],
        "dataset_rows": info["num_rows"], "source": "parquet", "shards": list(shards), "shard_rows": total,
        "sample_rows": len(out), "seed": seed, "max_chars": max_chars,
    })


def _write(out, out_path, manifest):
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    with open(out_path, "w") as f:
        for r in out:
            f.write(json.dumps(r) + "\n")
    manifest["fetched_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    manifest["note"] = "CFPB stopped publishing narratives on 2026-08-14; this is a CC0 mirror of earlier releases."
    dates = sorted(r["date_received"] for r in out if r["date_received"])
    if dates:
        manifest["date_range"] = [dates[0], dates[-1]]
    with open(out_path + ".manifest.json", "w") as f:
        json.dump(manifest, f, indent=2)
    return manifest


def fetch_sample_api(n, out_path, seed=7, run_length=20, max_chars=1500, workers=2):
    """Sample via the datasets-server rows API (no download, but rate-limited for anonymous use; set HF_TOKEN)."""
    info = dataset_info()
    rng = random.Random(seed)
    total = info["num_rows"]
    need_calls = max(1, int(n * 1.35 / run_length) + 1)        # over-fetch: unmapped products and duplicates
    offsets = sorted({rng.randrange(0, total - run_length) for _ in range(need_calls)})
    seen, out = set(), []
    with ThreadPoolExecutor(workers) as ex:
        for i, rows in enumerate(ex.map(lambda o: _rows(o, run_length), offsets), 1):
            for row in rows:
                r = normalise(row, max_chars)
                if r and r["text_hash"] not in seen and r["complaint_id"] not in seen:
                    seen.update((r["text_hash"], r["complaint_id"]))
                    out.append(r)
            if i % 50 == 0:
                print(f"  fetched {i}/{len(offsets)} pages, {len(out)} usable rows", flush=True)
    rng.shuffle(out)
    out = out[:n]
    return _write(out, out_path, {
        "dataset": DATASET, "config": CONFIG, "split": SPLIT, "revision": info["sha"], "license": info["license"],
        "dataset_rows": total, "source": "rows-api", "sample_rows": len(out), "seed": seed,
        "run_length": run_length, "max_chars": max_chars, "pages": len(offsets),
    })
