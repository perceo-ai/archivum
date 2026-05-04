from __future__ import annotations

import random
from typing import Protocol

from .types import MarketSnapshot, PortfolioState, ProposedOrders


class Strategy(Protocol):
    """Contract for producing trades from (portfolio state, market snapshot)."""

    def propose(
        self,
        state: PortfolioState,
        market: MarketSnapshot,
        *,
        rng: random.Random | None = None,
    ) -> ProposedOrders:
        """Return proposed orders for the next execution step."""


__all__ = ["Strategy"]
