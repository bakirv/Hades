# Hades — Technical Audit

**Date:** 2026-07-22 · **Version audited:** documented `v0.9.0` (pyproject still `0.6.0` — see L4)
**Auditor role:** Principal Software Architect + Senior Quant Engineer, adversarial review
**Scope:** `backend/` (407 source files, ~40.6k LOC, 57 tables, 7 migrations), `frontend/`, `infra/`, Docker, docs.

> This is an **evidence-based** audit. Every finding below cites a file/line or a
> reproducible command. Where a claim could not be *executed* (load/chaos tests need
> the live Docker stack), it is marked **NOT EXECUTED** and analysed statically rather
> than asserted. Nothing here is taken on faith from the docs.

---

## 0. Executive summary

Hades is, structurally, a **genuinely well-engineered platform**. The money-safety
invariants it advertises are real and hold under inspection (§2). The type system is
clean under strict mypy across **all 407 files**, **376/376 tests pass**, and there are
no god-classes, no stray `TODO`s, and disciplined fail-closed error handling.

It is **not yet production-ready for continuous LIVE operation** — and, correctly, it
*cannot* go live today (no signer/quote/RPC live adapters are wired; the engine is
paper-only by construction). The gaps that must close *before* LIVE is ever enabled are
concentrated in **durability** (the execution ledger and event store are in-memory) and
**API/WebSocket authentication** (off by default). None of these threaten the current
paper-only posture; all of them are blockers for real funds.

**Health baseline (reproduced this session):**

| Check | Result |
|---|---|
| `pytest -q` | **376 passed** in 103s |
| `mypy src` (strict) | **Success: no issues in 407 files** |
| `ruff check src` | 9 findings — all `UP046` (PEP-695 style), cosmetic |
| Broad `except Exception` | 154 (fail-safe by design); **1** true `pass` swallow |
| `TODO/FIXME/HACK` | 0 |

**Findings by severity:** 0 CRITICAL-now · 5 HIGH (all LIVE-gating) · 6 MEDIUM · 4 LOW.
Two MEDIUM items were **fixed in this pass** (M1, M5).

---

## 1. What was verified vs. not

| Area | Method | Depth |
|---|---|---|
| Architecture / SOLID / DDD / CQRS | Static read + import-graph checks | High |
| Money-safety invariants | Traced every call site + event publisher | High |
| Security (keys, auth, logging, Docker) | Read + grep + config review | High |
| Persistence / durability | Composition-root + runtime wiring trace | High |
| DB schema / indexes / migrations | Migration + model inspection | Medium |
| Scanner / Security Engine / AI Committee / Risk | Code-path read | Medium |
| **Load tests** (1000s tokens/wallets/events) | **NOT EXECUTED** — needs live stack | Static only |
| **Resilience/chaos** (RPC/Redis/PG down) | **NOT EXECUTED** — needs live stack | Static only |
| Runtime CPU/RAM/latency profiling | **NOT EXECUTED** — needs live stack | Static only |

The three NOT-EXECUTED areas require standing up Postgres + Redis + a Solana RPC and
driving synthetic load. They are analysed in §11–12 and scheduled in the roadmap, but no
numeric result is fabricated for them.

---

## 2. Money-safety invariants — VERIFIED ✅

These are the claims the whole platform's safety rests on. Each was traced to source.

| Invariant | Verdict | Evidence |
|---|---|---|
| Only the Risk Manager can authorise a trade | ✅ Holds | `TradeApproved(...)` is constructed in exactly one place: `risk/application/manager.py:305`. No other publisher exists. |
| Execution never runs without an approval | ✅ Holds (as wired) | In production the engine is driven only by the `TradeApproved` subscription (`ops/execution_runtime.py:85`). `engine.execute()` is public but called directly only in tests. |
| A config file alone can never route real orders | ✅ Holds | Live executor is built only if `settings.live_trading_enabled` **and** signer+quote+rpc are all present (`execution/application/factory.py:_maybe_build_live`). Paper is mandatory (`engine.__init__` raises without it). |
| Mode resolution fails safe | ✅ Holds | `_resolve_mode()` returns `paper` on unknown mode **or** any exception (`engine.py`). |
| Risk Manager is fail-closed | ✅ Holds | `evaluate()` wraps `_decide()`; any exception → `REJECT` (`manager.py:111`). Global gates (emergency → breaker → kill-switch) run before any token-specific logic. |
| The wallet layer never touches key material | ✅ Holds | `WalletManager` reads pubkey/balance/health only; keys live solely in the `TransactionSigner` adapter loaded from a mounted secret (`wallet_manager.py`, `execution/domain/ports.py:41`). |
| Research Lab cannot reach execution | ✅ Holds — **structurally enforced** | `tests/test_research_isolation.py` AST-parses every research file and fails the build if it imports `execution`/`risk`/`portfolio`; also asserts promotion payloads carry no `order`/`size_usd` and require `manual_approved`. |

This is the strongest part of the system and it is real, not aspirational.

---

## 3. Architecture review

**Verdict: NEEDS IMPROVEMENT (durability), otherwise strong.**

**Strengths.** Clean bounded contexts (`contexts/*` each split domain/application/
infrastructure), a real shared kernel, event-driven decoupling via an `EventBus` port
with in-memory *and* Redis Streams implementations, CQRS command/query buses, ports-and-
adapters throughout (every store has a `Protocol` port + In-Memory + Postgres adapter).
No circular context dependencies were found; the research→execution direction is
AST-blocked. Largest file is 755 lines (`config/settings.py`) — no god-objects.

**Weaknesses.**

- **A3.1 — "Event-sourcing" is overstated.** The `EventStore` is hardcoded
  `InMemoryEventStore()` in the composition root regardless of the database
  (`bootstrap.py:308`, comment: *"Postgres-backed store: later phase"*). The system is
  accurately described as **event-driven with persisted read-models**, not event-sourced
  with a durable log. There is no schema or migration for an events table. → **H1.**
- **A3.2 — Execution has no persistence adapter at all.** `execution/infrastructure/
  stores.py` contains only `InMemoryOrderStore` / `InMemoryTransactionStore`; no Postgres
  variant exists, and `execution_runtime` never passes one, so the order/fill ledger is
  in-memory in every configuration. There is no `0008_execution_tables` migration. → **H2.**
- **A3.3 — In-memory position map in the engine.** `ExecutionEngine._open` (a dict of
  open positions keyed by mint) is process memory. It is the source of entry-notional for
  realized-PnL on close. → **H3.**

**Documentation drift.** hades.md and the memory index describe the platform as
event-sourced and imply a durable ledger; §A3.1–A3.3 contradict that. This section and the
new hades.md audit block reconcile the record.

---

## 4. Security review

**Verdict: NEEDS IMPROVEMENT — acceptable for paper/localhost, blockers before LIVE.**

**Good.** No secret is hardcoded; `.env.example` documents the wallet key as a mounted
secret (`WALLET_KEYPAIR_PATH=/run/secrets/hades_wallet.json`) with a per-tx cap
(`WALLET_MAX_SOL_PER_TX=0.5`). CORS defaults to an explicit origin, not `*`. Keys never
enter application code. No private key, signature, or serialized-tx payload is logged (the
live executor logs only mint + error strings). The paper/live posture is announced loudly
at boot (`bootstrap.py`).

**Findings.**

- **H4 — API auth is OFF by default and the paper→live switch is unauthenticated.**
  `ApiSettings.auth_enabled = False` (`settings.py:51`). With auth off, `get_principal`
  returns a `system` principal and every route proceeds — including
  `POST` trading-mode change (`api/routers/trading.py`), config import, and kill-switch
  controls. This is safe *today* (live can't be built) but is a hard gate before LIVE.
- **H5 — WebSocket endpoints have no authentication.** `api/ws/routes.py` calls
  `websocket.accept()` with no key/principal check, even when API auth is enabled. Any
  client that can reach the port receives the live dashboard stream.
- **M1 — Non-constant-time API-key comparison.** *(FIXED this pass.)* `x_api_key ==
  api.auth_api_key` leaked timing; replaced with `hmac.compare_digest` in `security.py`.
- **M4 — Container hardening.** Services run as **root** (no `user:` in
  `docker-compose.yml`), no `cap_drop`, no `read_only` root FS. Prometheus/Grafana are
  pinned to `:latest` (non-reproducible builds) and bind `0.0.0.0` (`9090`, `3001`).

No sensitive data was found in logs. The audit trail (`contexts/audit`) persists to
Postgres when the DB is present.

---

## 5. Component audits (condensed)

### 5.1 Scanner — READY (paper)
RPC Manager with health-scored multi-provider failover, six independent DEX adapters, a
back-pressured acquisition pipeline, quality validator, and versioned features. Design is
sound. **NOT EXECUTED:** real rate-limit/latency/CPU behaviour under thousands of
tokens/sec — the in-memory snapshot/feature caches are the first place to watch for
unbounded growth under sustained load (§11).

### 5.2 Security Engine — READY
Ten pure analyzers over an assembled context, conservative critical-flag veto, rug/honeypot
composite scoring, wallet clustering, developer reputation, append-only black/white lists,
and explainable drivers/risks. Conservative-by-default (false-positive-biased), which is
the correct posture for meme-coin rug avoidance. False-negative coverage ultimately depends
on live data quality — track post-hoc via the outcome ledger.

### 5.3 AI Committee — READY (advisory)
12 transparent logistic specialists → meta model, append-only versioned registry with
human-gated promotion, shadow models, drift monitor, explainability + feature importance.
Pure-Python, no heavy ML. It only *quantifies* — never decides or sizes. **Data-leakage /
overfitting risk is procedural, not structural**: the code supports validation gauntlets
and drift detection, but the guarantee that no future-leaking feature enters a dataset lives
in how datasets are built at runtime, which cannot be certified statically. Recommend an
explicit leak-check (train/serve feature-timestamp assertion) in the training gauntlet.

### 5.4 Risk Manager — READY, invariants verified (§2)
Position sizing (conviction-weighted, kill-switch-scaled), exposure/allocation policies,
drawdown, correlation, kill switch, circuit breaker, emergency mode, all fail-closed and
ordered defensively. No path bypasses it (§2).

### 5.5 Execution Engine — NEEDS IMPROVEMENT
Paper executor is faithful; live executor is fail-closed (quote→slippage→sign→send→confirm,
any failure → failed fill, never optimistic) and correctly gated. **But:** order/txn ledger
and open-position map are in-memory (H2/H3), and realized-PnL on close subtracts only the
sell-side fee and assumes a full close (**M6**) — fine for the current single-position-per-
mint model, fragile if partial exits are ever added.

### 5.6 Research Lab — READY, isolation verified (§2)
Backtest (net of frictions), walk-forward, Monte Carlo, optimizer (multi-objective, never
ROI-alone), shadow, validation gauntlet, fail-closed human-gated promotion, knowledge base.
Structurally cannot modify production (AST test). **Note (H1):** "replay" has no durable
event stream to replay from until the event store is persisted.

### 5.7 Database — READY (read-models) / NEEDS IMPROVEMENT (coverage)
7 migrations, 57 tables, 190 index declarations, 34 FK/`ondelete` clauses. Read-model
persistence is real and conditional on `container.database` (always set in prod). Gaps: no
execution schema (H2), no event-store schema (H1). **NOT EXECUTED:** query-plan/lock/N+1
analysis under load.

### 5.8 Dashboard / WebSocket — NEEDS IMPROVEMENT
Read-only screens; WS has no auth (H5). Memory/CPU/latency under many concurrent sockets is
**NOT EXECUTED**. The WS fan-out (`api/ws/manager.py`) broadcasts to all connections — check
for slow-consumer backpressure before exposing publicly.

### 5.9 Watchdog / Health — READY (design)
Liveness heartbeat loop per service, health checks, metrics server, Redis-bus consumer
lifecycle, graceful shutdown with teardown ordering. Auto-recovery/restart is delegated to
Docker `restart: unless-stopped`. **NOT EXECUTED:** actual failover behaviour under crash.

---

## 6. Findings register

| ID | Sev | Component | Finding | Status |
|---|---|---|---|---|
| H1 | HIGH | Platform | Event store in-memory in prod; "event-sourcing" not durable | Open |
| H2 | HIGH | Execution | Order/transaction ledger not persisted (no Postgres store, no migration) | Open |
| H3 | HIGH | Execution | Open-position map in-memory → post-restart SELL mis-computes realized PnL | Open |
| H4 | HIGH | API | Auth off by default; paper→live switch endpoint unauthenticated | Open (LIVE-gating) |
| H5 | HIGH | WebSocket | No auth on WS endpoints even when API auth enabled | Open |
| M1 | MED | API | Non-constant-time API-key comparison | **Fixed** |
| M2 | MED | Platform | No graceful degradation when Postgres unreachable at runtime | Open |
| M3 | MED | Cross-cutting | 154 broad `except Exception`; 1 true `pass` swallow to annotate | Open |
| M4 | MED | Docker | Root containers, no cap_drop/read_only, `:latest` for prom/grafana | Open |
| M5 | MED | Execution | Dead `_executor_for` method; docstring inaccurate | **Fixed** |
| M6 | MED | Execution | Realized PnL ignores buy-side fee; assumes full close | Open |
| L1 | LOW | Style | 9 ruff `UP046` (PEP-695 type params) | Open (cosmetic) |
| L2 | LOW | CI | Toolchain drift: runs under Py3.14/pytest9/mypy2.1/ruff0.15 vs. older pins | Open |
| L3 | LOW | Tests | Starlette TestClient httpx deprecation warning | Open |
| L4 | LOW | Meta | `pyproject` version `0.6.0` lags documented `v0.9.0` | Open |

---

## 7. Fixes applied in this audit pass

1. **M1 — constant-time API key check.** `api/security.py` now imports `hmac` and uses
   `hmac.compare_digest(x_api_key, api.auth_api_key)`.
2. **M5 — dead code / honest docstring.** `ExecutionEngine.execute` now dispatches through
   `self._executor_for(mode)` (previously an unused method; `execute` indexed the dict
   directly). The mode-confinement docstring is now true, and the defensive paper-fallback
   in `_executor_for` is actually exercised.

Both changes verified: `pytest -k "execution or api or security"` → **111 passed**; `mypy`
on the two files → clean. No behavioural change in the happy path; strictly hardening.

---

## 8. Production readiness

**Rule honoured:** no component classed CRITICAL may enable LIVE. LIVE is *already*
structurally disabled (no live adapters), so the platform is safe today. The table below
uses **CRITICAL-for-LIVE** to mean "must be fixed before real funds", not "unsafe now".

| Component | Paper posture | Before LIVE |
|---|---|---|
| Risk Manager | READY | READY |
| Research Lab (isolation) | READY | READY |
| Security Engine | READY | READY |
| AI Committee | READY | NEEDS IMPROVEMENT (add explicit leak-check) |
| Scanner | READY | NEEDS IMPROVEMENT (load-validate) |
| Execution — paper | READY | READY |
| Execution — durable ledger (H2/H3) | NEEDS IMPROVEMENT | **CRITICAL-for-LIVE** |
| Execution — live adapters | NOT BUILT (correctly gated) | **CRITICAL-for-LIVE** (must build + audit) |
| Event store durability (H1) | NEEDS IMPROVEMENT | **CRITICAL-for-LIVE** |
| API auth (H4) | NEEDS IMPROVEMENT | **CRITICAL-for-LIVE** |
| WebSocket auth (H5) | NEEDS IMPROVEMENT | **CRITICAL-for-LIVE** |
| DB read-models | READY | READY |
| Docker hardening (M4) | NEEDS IMPROVEMENT | NEEDS IMPROVEMENT |
| Watchdog | READY (design) | NEEDS IMPROVEMENT (chaos-validate) |
| Dashboard | READY | NEEDS IMPROVEMENT (WS auth + load) |

**Gate verdict:** **DO NOT enable LIVE** until every CRITICAL-for-LIVE row is closed and
load + resilience suites (§11–12) have been executed against a real stack.

---

## 9. Roadmap

### High priority (LIVE-gating)
1. **Durable execution ledger** — `PostgresOrderStore` + `PostgresTransactionStore` +
   migration `0008`; wire them in `execution_runtime`. (H2)
2. **Persist open positions** — move `ExecutionEngine._open` to a repository (or rebuild
   from the portfolio read-model on boot); fix realized-PnL to use the stored entry. (H3, M6)
3. **Durable event store** — Postgres-backed `EventStore` + migration; enables real
   event-sourced replay for the Research Lab. (H1)
4. **API auth on by default in non-dev + enforce on state-changing routes**; require an
   operator principal for the paper→live switch specifically. (H4)
5. **WebSocket authentication** — API key / short-lived token at `accept()`. (H5)
6. **Build + independently audit the live adapters** (signer, quote provider, RPC gateway).

### Medium priority
7. Postgres degradation strategy — readiness gating + a DB circuit breaker so a DB outage
   fails writes loudly and pauses new entries instead of throwing per-event. (M2)
8. Container hardening — non-root `user:`, `cap_drop: [ALL]`, `read_only` where possible,
   pin Prometheus/Grafana image digests, bind admin ports to localhost. (M4)
9. AI Committee train/serve leak assertion in the validation gauntlet.
10. Audit the 154 broad catches — convert the 1 silent `pass` to a logged/annotated case;
    add error-rate metrics where missing. (M3)

### Low priority / quick wins
11. Re-pin dev toolchain (or widen CI matrix) to the versions actually in use; document that
    strict-clean is validated under Py3.14/mypy2.1. (L2)
12. Adopt PEP-695 type parameters to clear the 9 `UP046` findings, or pin ruff. (L1)
13. Bump `pyproject` version to match the documented release. (L4)
14. Silence/allow-list the Starlette TestClient deprecation. (L3)

### Future / risks to watch
15. Bounded-memory policy for in-memory caches (scanner snapshots/features) under sustained
    load — LRU/TTL caps before public exposure. (§11)
16. WS slow-consumer backpressure before exposing the dashboard beyond localhost.
17. Partial-exit accounting model if position management evolves past one-position-per-mint.

---

## 10. Optimization opportunities (static)

- **I/O / queries:** read-model repos already batch; the durability work (H1/H2) will add
  write volume — use batched inserts and an append-only, index-light events table.
- **Memory:** the biggest RAM risk is unbounded in-memory stores/caches under load — cap
  them (roadmap 15). This is more impactful than any micro-optimization.
- **Concurrency:** the single-process in-memory `EventBus` fans out sequentially per
  handler; on the Redis transport this scales across services. For high event rates, prefer
  the Redis transport in prod (already supported) and keep handlers idempotent (the bus is
  at-least-once by contract).
- **CPU:** no hot-path profiling was run; the Security Engine's ~10 analyzers per token and
  the AI Committee's per-token specialist ensemble are the natural first profiling targets.

---

## 11. Load tests — NOT EXECUTED (plan)

Requires the Docker stack (Postgres + Redis + a mock/real RPC). Proposed harness:

- Feed N∈{1k, 10k, 100k} synthetic tokens and wallets through the scanner→security→
  committee→risk→paper-execution pipeline; measure end-to-end latency, throughput, and RSS.
- **Primary hypotheses to falsify:** (a) in-memory snapshot/feature caches grow unbounded;
  (b) the event store (in-memory) grows unbounded and is the first OOM; (c) sequential
  bus fan-out becomes the latency bottleneck before RPC does.

Until run, no numeric SLA can be claimed. This is the single biggest gap between "works" and
"proven".

## 12. Resilience / chaos — NOT EXECUTED (plan)

- **RPC down:** the RPC Manager has documented health-scored failover — validate it empirically.
- **Postgres down:** today domain writes throw (M2) — chaos-test and add graceful pause.
- **Redis down:** if `EVENT_BUS_TRANSPORT=redis`, publish/consume fails — verify the
  service degrades rather than crashes; the in-memory transport is unaffected.
- **Worker/API/dashboard crash:** Docker `restart: unless-stopped` recovers the process, but
  in-memory state (H1/H2/H3) is lost — this is exactly why the durability roadmap is
  LIVE-gating.

---

## 13. How to reproduce this audit

```bash
cd backend
python -m pytest -q                 # 376 passed
python -m mypy src                  # Success: 407 files
python -m ruff check src            # 9 UP046 (cosmetic)
grep -rn "InMemoryEventStore()" src/hades/bootstrap.py      # H1
grep -rn "class .*Store" src/hades/contexts/execution/infrastructure/stores.py  # H2 (in-memory only)
grep -n "auth_enabled" src/hades/shared_kernel/config/settings.py               # H4
grep -rn "websocket.accept" src/hades/api/ws/                                   # H5
```
