"""Reputation Engine — evolve a wallet's non-binary reputation over time.

Reputation is never a boolean and never set in one shot. Each observation nudges
the components toward a *target* implied by the evidence, blended with the prior
by an exponential moving average so a single event cannot swing a long history,
yet sustained behaviour eventually dominates. New wallets start neutral (50) with
zero experience — unknown is a mild caution, never a free pass and never a
condemnation.

Pure: no I/O, fully deterministic in its inputs. It answers *how trustworthy does
the evidence say this wallet is*, not *should we trade*.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import log1p

from hades.contexts.intelligence.domain.models import ReputationScores


@dataclass(frozen=True)
class ReputationEvidence:
    """The measured aggregates a wallet's reputation is derived from."""

    tokens_traded: int
    launches: int
    rugs_participated: int
    successes: int
    age_hours: float
    is_known_scammer: bool
    #: 0..1 — how regular the wallet's sizing/timing is (1 = very consistent).
    consistency_signal: float = 0.5


def _clamp(value: float) -> float:
    return max(0.0, min(100.0, value))


def _ewma(prior: float, target: float, alpha: float) -> float:
    return _clamp((1.0 - alpha) * prior + alpha * target)


class ReputationEngine:
    """Folds fresh evidence into an evolving :class:`ReputationScores`."""

    def __init__(self, *, alpha: float = 0.25) -> None:
        # Learning rate: how fast a component moves toward new evidence.
        self._alpha = alpha

    def evolve(self, prior: ReputationScores, evidence: ReputationEvidence) -> ReputationScores:
        if evidence.is_known_scammer:
            # A confirmed scammer is a hard reputational floor: trust collapses and
            # risk maxes. This is evidence, not an assumption.
            return prior.model_copy(
                update={
                    "trust": _ewma(prior.trust, 0.0, 0.6),
                    "risk": _ewma(prior.risk, 100.0, 0.6),
                    "experience": prior.experience,
                    "consistency": prior.consistency,
                    "profitability": _ewma(prior.profitability, 10.0, 0.5),
                }
            )

        resolved = evidence.rugs_participated + evidence.successes
        rug_rate = evidence.rugs_participated / resolved if resolved else None
        success_rate = evidence.successes / resolved if resolved else None

        # Trust rises with clean participation and successes, falls with rugs.
        trust_target = 50.0
        if rug_rate is not None:
            trust_target = _clamp(80.0 - 90.0 * rug_rate)
        elif evidence.successes:
            trust_target = 65.0
        # Risk is the mirror: rug involvement is the dominant risk driver.
        risk_target = 50.0
        if rug_rate is not None:
            risk_target = _clamp(15.0 + 85.0 * rug_rate)
        elif evidence.tokens_traded == 0:
            risk_target = 55.0  # brand-new wallet: mild caution

        # Experience grows (saturating) with breadth of activity and longevity.
        exp_target = _clamp(
            18.0 * _log1p(evidence.tokens_traded)
            + 6.0 * _log1p(evidence.launches)
            + 10.0 * _log1p(evidence.age_hours / 24.0)
        )
        # Profitability proxied by success rate until PnL estimation exists.
        prof_target = 50.0
        if success_rate is not None:
            prof_target = _clamp(25.0 + 60.0 * success_rate)

        consistency_target = _clamp(100.0 * evidence.consistency_signal)

        return ReputationScores(
            trust=_ewma(prior.trust, trust_target, self._alpha),
            risk=_ewma(prior.risk, risk_target, self._alpha),
            consistency=_ewma(prior.consistency, consistency_target, self._alpha),
            # Experience only ever accrues — it is a ratchet, not an average.
            experience=max(prior.experience, exp_target),
            profitability=_ewma(prior.profitability, prof_target, self._alpha),
        )


def _log1p(value: float) -> float:
    return log1p(max(0.0, value))
