"""Monitoring context — Watchdog + Health Monitor for 24/7 operation.

Responsibility:
    * Collect heartbeats from every long-running component (scanner loop, worker,
      price feeds) and flag any that miss beats (the Watchdog).
    * Aggregate liveness + dependency checks (db, redis, RPC) into an overall
      system health verdict consumed by the API ``/health`` endpoint and probes.
    * Emit ``ComponentHeartbeat``, ``HealthDegraded``, ``HealthRecovered`` so the
      Notification context can alert on outages.

Designed for years of unattended uptime: everything is observable, nothing fails
silently.

Phase 1 scope: contracts + health model (used by the live ``/health`` endpoint).
"""
