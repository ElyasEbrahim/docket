# Draft upstream issue for realZachi/pg-jev (not filed)

> Review before posting. It was found and reproduced by the Phase 0 harness (`make cachecheck`).

---

**Title:** Session answer cache ignores `jev.model` and `jev.api_url`: switching backend or model mid-session returns stale answers

**Version:** 0.2.1 (PostgreSQL 16, Docker)

**What happens**

`_jev_eval` keys its per-session cache on `[rel_type, query, kind, options]` (`sql/jev--0.2.1.sql`, `cache_key = json.dumps([rel_type, query, kind, opts], sort_keys=True)`). Neither `jev.model` nor `jev.api_url` is part of the key. After a `SET jev.model = ...` or `SET jev.api_url = ...` in the same session, `jev()`, `jev_prob()` and the other functions keep returning answers from the previous model or backend, without warning, until `jev_cache_clear()`.

**Reproduction** (2,000-row table, two Jev-compatible local servers that give different answers)

```sql
SET jev.api_url = 'http://mock:8765/local/v1/systemone';
SELECT md5(i.narrative), jev_prob(i, 'the complaint is about a debt collector or about collecting a debt') FROM bench.items i;
SET jev.api_url = 'http://sim:8787/v1/systemone';
SELECT md5(i.narrative), jev_prob(i, 'the complaint is about a debt collector or about collecting a debt') FROM bench.items i;
```

Result: all 2,000 answers from the second query are identical to the first backend's. In a fresh session against the second backend, 0 of 2,000 match.

**Why it matters**

- Pinning `jev.model = 'jev-1.13.0'` (as the docs recommend for reports) after an exploratory `jev-latest` query silently keeps the `jev-latest` answers.
- Comparing a hosted backend with a local one (stuntd, laya-server), which 0.2.1 explicitly enables, gives a false "identical" result.
- `ALTER ROLE ... SET jev.model` does not help pooled sessions that already cached answers.

**Suggested fix**

Include the effective `model` and the normalised `api_url` (scheme, host, port, path) in `cache_key`. `load_cfg()` already reads both, but the cache-hit path deliberately skips SPI. Options:

1. Read the two GUCs in the cache-hit path too (one extra SPI call per hit), or
2. Keep a per-statement memo keyed on `statement_timestamp()` so the settings are read once per statement, as the spend guard already does, and fold them into the key.

A regression test could run the same query against `/local/...` on the mock with two different `jev.model` values and assert that the mock sees two sets of requests.
