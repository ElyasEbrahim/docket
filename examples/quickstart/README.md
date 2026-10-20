# pgdocket in 5 minutes

You need Docker and a TypeSafe API key ([console.typesafe.ai](https://console.typesafe.ai)). The whole quickstart costs about **$0.001** in API calls.

The database holds 60 **synthetic** support tickets (written for this example; see `seed.sql`). Each has a `team` column: the team a person routed it to. pgdocket will decide the team for every ticket, keep that decision current, and learn from the `team` labels how far to trust itself.

```bash
cd examples/quickstart
export TYPESAFE_API_KEY=...          # or put it in a .env file next to docker-compose.yml
docker compose up -d --wait db
```

**1. Install the schema.** This needs no superuser and no extension:

```bash
docker compose run --rm pgdocket install
# applied: 001
```

**2. Declare the decision.** Existing rows are queued; new and edited rows will be too:

```bash
docker compose run --rm pgdocket create triage --table shop.tickets --key id --text subject,body \
  --kind choice --question "Which team should handle this support ticket?" \
  --options billing,technical,account,sales
# decision triage (id 1) created; 60 rows queued; read it from docket.v_triage
```

**3. Start the worker.** It judges the queue, then waits for new rows:

```bash
docker compose up -d pgdocket
docker compose exec db psql -U postgres -d shop -c \
  "SELECT key, status, answer, round(confidence::numeric, 2) AS confidence FROM docket.v_triage ORDER BY key LIMIT 5"
#  key | status |  answer   | confidence
#    1 | judged | billing   |       1.00
#    2 | judged | technical |       1.00
#    3 | judged | account   |       0.81
```

**4. Add a ticket and watch it get decided** (about a second):

```bash
docker compose exec db psql -U postgres -d shop -c \
  "INSERT INTO shop.tickets (id, subject, body) VALUES (61, 'Charged for a seat we removed', 'We removed a user last month but the invoice still includes their seat.')"
docker compose exec db psql -U postgres -d shop -c "SELECT key, status, answer FROM docket.v_triage WHERE key = 61"
#  61 | judged | billing
```

**5. Calibrate on your labels.** Raw confidence is not a probability yet:

```bash
docker compose run --rm pgdocket label triage --from-column team
docker compose run --rm pgdocket calibrate triage --precision-target 0.85
# triage: 60 labels · calibration error 0.071 → 0.040 · auto-accept at ≥ 0.542: 100.0 % of rows with precision ≥ 85 % (95 % confidence)
```

**6. Act on the answers you can trust:**

```bash
docker compose exec db psql -U postgres -d shop -c \
  "SELECT key, answer, round(confidence::numeric, 2) AS confidence, auto FROM docket.v_triage ORDER BY confidence LIMIT 3"
#  59 | account | 0.52 | f      ← below the threshold: send to a person
#  24 | sales   | 0.57 | t
#  33 | billing | 0.62 | t
```

`auto = true` means the answer clears the threshold that keeps precision ≥ 85 % at 95 % confidence.

**Why 85 % and not 90 %?** With only 60 labels, even 58 of 60 correct can't *prove* 90 % at 95 % confidence, so `calibrate --precision-target 0.9` honestly reports that no threshold qualifies. More labels make stricter targets provable. 100–200 is a good start.

**Check the decision against your labels** in a full report (agreement, calibration, thresholds, cost):

```bash
docker compose run --rm --user root -v "$PWD/reports:/reports" pgdocket check \
  --table shop.tickets --key id --text subject,body \
  --kind choice --question "Which team should handle this support ticket?" \
  --options billing,technical,account,sales --label-column team --sample 60 --yes --out /reports/triage
# report: /reports/triage/report.md   → open reports/triage/report.md
```

**Clean up:** `docker compose down -v`

Your numbers may differ slightly: the model doesn't return identical probabilities on every run (see the [findings](../../docs/phase0/FINDINGS-jev-1.13.md)). Next: [pgdocket/README.md](../../pgdocket/README.md) for all options, and [docs/phase1/ledger.md](../../docs/phase1/ledger.md) for how it works.
