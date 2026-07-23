"""Pool features — size, depth, concentration, LP lock and liquidity change."""

from __future__ import annotations

from hades.contexts.features.domain.models import FeatureInputs


class PoolFeatures:
    """Liquidity-pool structure and its recent change."""

    @property
    def namespace(self) -> str:
        return "pool"

    def compute(self, inputs: FeatureInputs) -> dict[str, float]:
        pool = inputs.pool
        if pool is None:
            return {
                "size_usd": 0.0,
                "depth_usd": 0.0,
                "concentration": 0.0,
                "lp_holders": 0.0,
                "lp_locked": 0.0,
                "lock_duration_seconds": 0.0,
                "liquidity_change_pct": 0.0,
                "lp_change_pct": 0.0,
                "has_pool": 0.0,
            }
        return {
            "size_usd": pool.size_usd,
            "depth_usd": pool.depth_usd,
            "concentration": pool.concentration,
            "lp_holders": float(pool.lp_holders),
            "lp_locked": 1.0 if pool.lp_locked else 0.0,
            "lock_duration_seconds": pool.lock_duration_seconds,
            "liquidity_change_pct": pool.liquidity_change_pct,
            "lp_change_pct": pool.lp_change_pct,
            "has_pool": 1.0,
        }
