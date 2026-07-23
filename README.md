# Hades

Professional quantitative platform for Solana, initially focused on meme coins.
Modular, decoupled, event-driven, and built to run 24/7 for years.

> **Full technical reference:** [`hades.md`](hades.md) — the living documentation.

## Quick start (Linux + Docker only)

```bash
make init          # create .env from .env.example — then edit your secrets
make up            # docker compose up -d
make migrate       # apply DB migrations
```

Then:
- API + docs → http://localhost:8000/docs
- Health → http://localhost:8000/health · Status → `/api/v1/status`
- Dashboard → http://localhost:5173
- Metrics → http://localhost:8000/metrics
- Backup now → `make backup`

Optional layers:

```bash
make up-all        # + ClickHouse (analytics) + Prometheus/Grafana (observability)
```

## Design in one paragraph

The platform is a modular monolith of independent **bounded contexts** (scanner,
features, security, wallet, market, scoring, risk, portfolio, execution,
learning, research, notification, monitoring) that communicate **only through
domain events**. It uses Clean Architecture, DDD, Event Sourcing and CQRS. The
Scoring Engine produces **probabilities, never decisions**; the Risk Manager
decides. Paper and live trading share the exact same decision engine — only the
Execution Engine adapter differs, and live trading is hard-gated behind two
switches.

## Status

**Phase 3 — Scanner (data acquisition)** (`v0.3.0`). On top of the Phase-2
platform, the Scanner continuously discovers, analyses and stores everything about
the Solana ecosystem — and never trades or decides. A multi-provider, health-
scored **RPC Manager** (auto-failover); a **Discovery Engine** fed by independent
DEX adapters (pump.fun, Raydium, Orca, Meteora, Jupiter, DexScreener); a
**Metadata Collector**; a **Feature Engine** (hundreds of versioned features); a
**Quality Validator**; a back-pressured **Acquisition Pipeline**; a **History
Builder** (snapshots); plus scanner metrics and a live dashboard screen. Still no
scoring, strategies or AI — those are later phases (see [`hades.md`](hades.md)
§6b, §9).

## Safety

Everything runs in Docker. All configuration and secrets live in `.env` (never
committed). Live trading is disabled by default and requires both
`HADES_TRADING_MODE=live` and `HADES_LIVE_TRADING_ENABLED=true`.
