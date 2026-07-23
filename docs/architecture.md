# Architecture notes

The authoritative architecture reference is [`../hades.md`](../hades.md). This
folder holds deeper design records (ADRs, diagrams) added as decisions are made.

## Architecture Decision Records (ADRs)

ADRs will be numbered `NNNN-title.md` here. The Phase 1/2 baseline is documented
in `hades.md` (see §6/§6a for the Phase 2 platform infrastructure).

Decisions realised in Phase 2 (candidates to formalise as ADRs retroactively):
- Postgres schema baseline — 26 tables built from `Base.metadata`
  (`alembic/versions/0001_initial_schema.py`); UUIDv7 pks + timestamps everywhere.
- Redis Streams event-bus transport with **per-service consumer groups** (every
  service sees every event) and an `EventRegistry` for cross-boundary rebuild.
- Background-service liveness via heartbeat files + Docker healthchecks
  (`--role`), the watchdog verifying freshness.
- Paper↔live switch: DB authority (`system_configuration`) ANDed with the hard
  env gate; audited, event-driven, notification-announced.

Candidate ADRs for upcoming phases:
- Postgres-backed event store + `UnitOfWork` (replace the in-memory fallback).
- Model registry format and promotion protocol.
