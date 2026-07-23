"""Acquisition Pipeline — ordered, parallel, back-pressured token processing.

Discovery hands each new candidate here. A bounded queue feeds a pool of workers
that run the ordered stages the spec mandates and never skip one:

    metadata -> validation -> storage -> events

(Market and Feature computation are separate contexts that react to the
``TokenDiscovered`` event this pipeline emits — that is the "market -> features"
part of the flow, kept decoupled per the event-driven architecture.)

The queue is bounded (``PIPELINE_QUEUE_MAX_SIZE``); when full the pipeline drops
the *oldest* pending candidate and counts it, so a burst of discoveries applies
backpressure instead of exhausting memory. Every stage is timed, and every error
or timeout is recorded — the pipeline is built to run for months unattended.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Coroutine
from typing import Any, TypeVar

from hades.contexts.scanner.application.metadata_collector import (
    CollectedMetadata,
    MetadataCollector,
)
from hades.contexts.scanner.application.metrics import ScannerMetrics
from hades.contexts.scanner.application.quality_validator import QualityValidator
from hades.contexts.scanner.domain.events import (
    DataQualityAnomalyDetected,
    PoolDiscovered,
    TokenDiscovered,
    TokenMetadataCollected,
)
from hades.contexts.scanner.domain.models import QualityIssue, ValidationOutcome
from hades.contexts.scanner.domain.ports import DiscoveryRepository, RawTokenCandidate
from hades.shared_kernel.config.settings import PipelineSettings
from hades.shared_kernel.domain.identifiers import new_id
from hades.shared_kernel.events import EventBus
from hades.shared_kernel.logging import get_logger

_logger = get_logger("scanner.pipeline")

_T = TypeVar("_T")


class AcquisitionPipeline:
    """A back-pressured worker pool that enriches, validates and stores tokens."""

    def __init__(
        self,
        collector: MetadataCollector,
        validator: QualityValidator,
        repository: DiscoveryRepository,
        *,
        settings: PipelineSettings,
        event_bus: EventBus,
        metrics: ScannerMetrics,
    ) -> None:
        self._collector = collector
        self._validator = validator
        self._repo = repository
        self._settings = settings
        self._bus = event_bus
        self._metrics = metrics
        self._queue: asyncio.Queue[RawTokenCandidate] = asyncio.Queue(
            maxsize=settings.queue_max_size
        )
        self._workers: list[asyncio.Task[None]] = []
        self._active = 0

    # -- lifecycle ------------------------------------------------------------

    async def start(self) -> None:
        self._workers = [
            asyncio.create_task(self._worker(i), name=f"pipeline-worker-{i}")
            for i in range(self._settings.workers)
        ]
        _logger.info("pipeline_started", workers=self._settings.workers)

    async def stop(self) -> None:
        for task in self._workers:
            task.cancel()
        await asyncio.gather(*self._workers, return_exceptions=True)
        self._workers = []

    def queue_depth(self) -> int:
        """Current number of candidates waiting to be processed."""
        return self._queue.qsize()

    def active_workers(self) -> int:
        """Number of workers currently processing a token."""
        return self._active

    async def enqueue(self, candidate: RawTokenCandidate) -> None:
        """Discovery sink. Applies backpressure by dropping the oldest if full."""
        if self._queue.full():
            try:
                self._queue.get_nowait()
                self._queue.task_done()
                self._metrics.backpressure_drops.inc()
            except asyncio.QueueEmpty:  # pragma: no cover — racing worker drained it
                pass
        await self._queue.put(candidate)
        self._metrics.queue_depth.set(self._queue.qsize())

    # -- workers --------------------------------------------------------------

    async def _worker(self, index: int) -> None:
        while True:
            candidate = await self._queue.get()
            self._metrics.queue_depth.set(self._queue.qsize())
            self._active += 1
            self._metrics.active_workers.set(self._active)
            try:
                await self._process(candidate)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self._metrics.processed.labels(outcome="error").inc()
                _logger.error(
                    "pipeline_process_failed",
                    worker=index,
                    mint=str(candidate.token.mint),
                    error=str(exc),
                )
            finally:
                self._active -= 1
                self._metrics.active_workers.set(self._active)
                self._queue.task_done()

    async def _process(self, candidate: RawTokenCandidate) -> None:
        started = asyncio.get_running_loop().time()
        correlation = new_id()
        token = candidate.token

        # Stage: storage of the raw identity (idempotent upsert).
        await self._stage("storage_token", self._repo.upsert_token(candidate))

        # Stage: metadata collection.
        collected = await self._stage("metadata", self._collector.collect(token), default=None)

        # Stage: validation (candidate + metadata) — records anomalies, never raises.
        await self._validate(candidate, collected, correlation)

        # Stage: storage of metadata + any pool.
        if collected is not None:
            await self._stage("storage_metadata", self._repo.save_metadata(collected.metadata))
        if candidate.pool is not None:
            await self._stage("storage_pool", self._repo.save_pool(candidate.pool))

        # Stage: events (announce the token so features/market/etc. react).
        await self._emit(candidate, collected, correlation)

        self._metrics.processed.labels(outcome="ok").inc()
        self._metrics.analysis_seconds.observe(asyncio.get_running_loop().time() - started)

    async def _validate(
        self,
        candidate: RawTokenCandidate,
        collected: CollectedMetadata | None,
        correlation: str,
    ) -> None:
        outcomes: list[ValidationOutcome] = [self._validator.validate_candidate(candidate)]
        if collected is not None:
            outcomes.append(self._validator.validate_collected(collected))
        for outcome in outcomes:
            for issue in outcome.issues:
                await self._record_anomaly(str(candidate.token.mint), issue, correlation)

    async def _record_anomaly(self, subject: str, issue: QualityIssue, correlation: str) -> None:
        self._metrics.anomalies.labels(kind=issue.kind.value).inc()
        try:
            await self._repo.record_anomaly(
                subject=subject,
                kind=issue.kind.value,
                field=issue.field,
                detail=issue.detail,
            )
        except Exception as exc:
            _logger.warning("anomaly_persist_failed", error=str(exc))
        await self._bus.publish(
            DataQualityAnomalyDetected(
                aggregate_id=new_id(),
                correlation_id=correlation,
                subject=subject,
                kind=issue.kind,
                field=issue.field,
                detail=issue.detail,
            )
        )

    async def _emit(
        self,
        candidate: RawTokenCandidate,
        collected: CollectedMetadata | None,
        correlation: str,
    ) -> None:
        ref = collected.metadata.as_ref() if collected is not None else candidate.token
        await self._bus.publish(
            TokenDiscovered(
                aggregate_id=new_id(),
                correlation_id=correlation,
                token=ref,
                source=candidate.source,
                initial_liquidity=candidate.liquidity,
                discovered_from_signature=candidate.signature,
            )
        )
        if collected is not None:
            await self._bus.publish(
                TokenMetadataCollected(
                    aggregate_id=new_id(),
                    correlation_id=correlation,
                    token=ref,
                    metadata=collected.metadata,
                )
            )
        if candidate.pool is not None:
            await self._bus.publish(
                PoolDiscovered(
                    aggregate_id=new_id(),
                    correlation_id=correlation,
                    token=ref,
                    pool=candidate.pool,
                    source=candidate.source,
                )
            )

    # -- stage helper ---------------------------------------------------------

    async def _stage(
        self,
        name: str,
        coro: Coroutine[Any, Any, _T],
        *,
        default: _T | None = None,
    ) -> _T | None:
        """Run one stage with timeout + timing, converting failures to metrics."""
        started = asyncio.get_running_loop().time()
        try:
            result = await asyncio.wait_for(coro, timeout=self._settings.stage_timeout_seconds)
        except TimeoutError:
            self._metrics.stage_timeouts.labels(stage=name).inc()
            _logger.warning("pipeline_stage_timeout", stage=name)
            return default
        except Exception as exc:
            self._metrics.stage_errors.labels(stage=name).inc()
            _logger.warning("pipeline_stage_error", stage=name, error=str(exc))
            return default
        finally:
            self._metrics.stage_seconds.labels(stage=name).observe(
                asyncio.get_running_loop().time() - started
            )
        return result


DiscoverySink = Callable[[RawTokenCandidate], Awaitable[None]]
