"""Build a :class:`Committee` from documented defaults or from the registry.

Two constructors:

* :func:`default_committee` — the committee seeded from documented priors, used
  before any model has been trained/promoted (so the brain is meaningful from
  day one).
* :func:`committee_from_cards` — reconstructs the active committee from promoted
  :class:`ModelCard`s, falling back to the default for any member/meta that has
  no promoted model yet. Because every model is a transparent weight set, this is
  a pure, exact reconstruction — no artefacts to load.
"""

from __future__ import annotations

from collections.abc import Sequence

from hades.contexts.learning.application.committee.base import SpecialistModel
from hades.contexts.learning.application.committee.manager import Committee
from hades.contexts.learning.application.committee.specialists import (
    SPECIALIST_SPECS,
    default_specialists,
)
from hades.contexts.learning.application.meta_model import MetaModel
from hades.contexts.learning.domain.models import META_MODEL_NAME, ModelCard


def default_committee(label: str = "active") -> Committee:
    """The committee built entirely from documented default weights."""
    return Committee(specialists=default_specialists(), meta=MetaModel(), label=label)


def committee_from_cards(cards: Sequence[ModelCard], label: str = "active") -> Committee:
    """Reconstruct the committee from promoted cards, defaulting where absent."""
    by_name = {card.name: card for card in cards}
    specialists: list[SpecialistModel] = []
    for member, spec in SPECIALIST_SPECS.items():
        card = by_name.get(member.value)
        if card is not None and card.weights.coefficients:
            specialists.append(SpecialistModel(spec, card.weights, version=card.version))
        else:
            specialists.append(SpecialistModel.from_defaults(spec))

    meta_card = by_name.get(META_MODEL_NAME)
    if meta_card is not None and meta_card.heads:
        meta = MetaModel(meta_card.heads, version=meta_card.version)
    else:
        meta = MetaModel()
    return Committee(specialists=tuple(specialists), meta=meta, label=label)
