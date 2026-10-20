# Phase 0 benchmark harness. Everything runs in Docker; nothing is installed on the host.
#
#   make up              build + start Postgres/pg-jev, the upstream mock and the simulated backend
#   make upstream-test   run pg-jev's own regression suite (v0.2.1) in a throwaway container
#   make smoke           pg-jev's README queries against the upstream mock
#   make test            unit tests
#   make itest           ledger integration tests (non-superuser, against the local Postgres)
#   make fetch load      CFPB sample → Postgres (N rows, default 2000)
#   make bench           run all experiments on BACKEND (sim | mock | jev) and write the report
#   make cachecheck      does pg-jev reuse answers across backends in one session?
#   make e2e             small end-to-end run on the simulated backend
#
# Real Jev:  TYPESAFE_API_KEY=... make bench BACKEND=jev ARGS=--yes   (refuses runs estimated above $1)

PG_JEV_REF ?= v0.2.1
BACKEND    ?= sim
N          ?= 2000
FETCH_N    ?= 3000
ARGS       ?=

COMPOSE = docker compose
BENCH   = $(COMPOSE) run --rm bench
PSQL    = $(COMPOSE) exec -T db psql -U postgres -d bench -v ON_ERROR_STOP=1

.PHONY: up down reset psql upstream-test smoke test itest fetch load bench analyze curve cachecheck e2e

up:
	$(COMPOSE) up -d --build --wait db mock sim

down:
	$(COMPOSE) down

reset:
	$(COMPOSE) down -v

psql:
	$(COMPOSE) exec db psql -U postgres -d bench

upstream-test:
	docker build -t docket-phase0/pg-jev-test:$(PG_JEV_REF) -f test/Dockerfile \
		https://github.com/realZachi/pg-jev.git#$(PG_JEV_REF)
	docker run --rm docket-phase0/pg-jev-test:$(PG_JEV_REF)

smoke: up
	$(PSQL) < harness/sql/smoke.sql

test:
	$(COMPOSE) run --rm --no-deps --entrypoint python bench -m pytest -q harness/tests pgdocket/tests

itest: up
	$(COMPOSE) run --rm -e TEST_DATABASE_URL=postgresql://postgres:bench@db:5432/bench --entrypoint python bench \
		-m pytest -q pgdocket/tests/test_ledger_pg.py

fetch:
	$(BENCH) fetch --n $(FETCH_N)

load:
	$(BENCH) load --n $(N)

bench:
	$(BENCH) run --backend $(BACKEND) --analyze $(ARGS)

analyze:
	$(BENCH) analyze --run $(or $(RUN),latest)

curve:
	$(BENCH) curve --run $(or $(RUN),latest)

cachecheck:
	$(BENCH) cachecheck

e2e: up
	$(BENCH) fetch --n 400 --out data/raw/cfpb_e2e.jsonl
	$(BENCH) load --input data/raw/cfpb_e2e.jsonl --n 300
	$(BENCH) run --backend sim --analyze --notes e2e
	$(BENCH) cachecheck
