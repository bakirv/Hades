# Changelog

Notable changes to Hades Core. Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/);
this project versions from `hades.__version__`.

Entries describe what changed for someone *operating* the platform, not the diff.

## [Unreleased]

### Fixed

- **Open positions are marked to market, and they close.** The platform could
  only buy. Nothing called `Position.mark()`, so `PositionUpdated` was never
  published and unrealised PnL stayed at exactly 0.00 for the life of every
  position; `OrderSide.SELL` was never issued anywhere outside tests, so nothing
  ever closed and realised PnL never moved. Since equity is cash + invested +
  unrealised, it never left the starting balance. Every figure on the Portfolio
  page was real code faithfully reporting a book that could not change.
  The new **Position Monitor** prices each open position on a tick, publishes the
  mark, and places the closing SELL through the ordinary execution path when a
  position hits its take-profit, stop-loss, trailing stop or time stop.
- **A price oracle exists.** No `PriceOracle` implementation had ever been
  written, so the Paper Executor's documented fallback — a $1 unit price — was
  the only path ever taken. Paper fills are now grounded in a real price, taken
  from the deepest pool rather than the first one returned.
- **Exit slippage costs something.** A SELL is denominated in the market value
  of what is being sold, so the impact belongs on the proceeds; it was being
  modelled like a BUY, which made a flat round trip cost only fees. Paper mode
  no longer reports profits the real market would never have paid.
- **`POSITION_*` thresholds are enforced, not just consulted.** Take-profit,
  stop-loss and trailing settings already existed and were read only to *size*
  trades. Nothing acted on them.

### Added

- `POSITION_MONITOR_ENABLED`, `POSITION_MONITOR_INTERVAL_SECONDS`,
  `POSITION_MAX_HOLD_MINUTES` (time stop, off by default).
- `EXECUTION_PRICE_ORACLE_*` — enable/URL/timeout/cache TTL.
- Metrics: `hades_execution_position_marks_total`,
  `..._marks_unpriced_total`, `..._position_exits_total{reason}`,
  `hades_execution_tracked_positions`.
- The Portfolio page lists the book position by position, with each position's
  unrealised PnL and ROI.
- `docs/OPERATING.md` gained a section on the Position Monitor, including the two
  settings whose "off" state looks exactly like the bug above.

### Changed

- **The dashboard is four sections instead of twelve flat entries.** System
  (Overview, Portfolio), Research (Lab, Scanner, Wallet Intel, AI), Configuration
  (Settings, Risk, Trading Mode) and Terminal. Every previous URL still resolves —
  `/health` and `/logs` redirect — so nothing that linked to a screen broke.
- **Risk shows the Risk Manager's live posture** — kill switch, circuit breaker,
  emergency mode, exposure against limits, and recent approve/reject decisions.
  It previously rendered `config.risk`, which the Settings tab already listed in
  full, while `/api/v1/risk/status` was served and displayed nowhere.
- **Logs merged into Terminal.** Both consumed the same stream and rendered it
  through the same component; Logs differed only by a minimum-level filter, which
  now lives in the Terminal.
- **Health merged into the System overview.** The overview's health panel was the
  Health screen, probe for probe. The hardcoded "Services" badge list beside it
  was removed: it looked like status and was a string array, so it stayed green
  while a service was down.

### Documentation

- `docs/RESEARCH_LAB_BRIDGE.md` documents how the Research Lab *produces* a
  candidate bundle. The document previously described a `CandidateExporter` in
  the lab repository that did not exist — Core could import a format nothing
  could write.

## [0.10.0]

Baseline for this changelog. See the git history for earlier work.
