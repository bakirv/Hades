"""Value objects enforce their invariants at construction."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from hades.contexts.common.domain.value_objects import (
    Money,
    Percentage,
    Probability,
    Score,
)


def test_money_arithmetic_same_currency() -> None:
    assert (Money(amount="10") + Money(amount="5")).amount == 15


def test_money_rejects_currency_mismatch() -> None:
    with pytest.raises(ValueError, match="currency mismatch"):
        _ = Money(amount="10", currency="USD") + Money(amount="1", currency="SOL")


def test_percentage_bounds() -> None:
    assert Percentage(value=25).as_fraction() == 0.25
    with pytest.raises(ValidationError):
        Percentage(value=150)


def test_probability_bounds() -> None:
    Probability(value=0.82)
    with pytest.raises(ValidationError):
        Probability(value=1.5)


def test_score_labels_and_comparison() -> None:
    assert Score(value=85).label == "excellent"
    assert Score(value=70) >= 60
    assert Score(value=30) < Score(value=50)
