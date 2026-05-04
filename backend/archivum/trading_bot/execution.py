from __future__ import annotations

import datetime as dt
import uuid
from dataclasses import dataclass
from typing import List, Sequence

from .types import ExecutionReport, Fill, MarketSnapshot, OrderRequest, OrderSide, OrderType


class ExecutionEngine:
    """Contract for turning orders into fills given a market snapshot."""

    def execute(self, orders: Sequence[OrderRequest], market: MarketSnapshot) -> ExecutionReport:  # pragma: no cover
        raise NotImplementedError


@dataclass
class NaiveBarExecutionEngine(ExecutionEngine):
    """Reference engine that fills market orders at bar.close.

    This is deliberately simple so it can be used as a contract-friendly
    placeholder for live/exchange integrations later.
    """

    fee_rate: float = 0.0  # e.g. 0.001 = 10 bps
    slippage_bps: float = 0.0

    def execute(self, orders: Sequence[OrderRequest], market: MarketSnapshot) -> ExecutionReport:
        fills: List[Fill] = []
        rejected: List[OrderRequest] = []

        for order in orders:
            bar = market.bars.get(order.symbol)
            if bar is None:
                rejected.append(order)
                continue

            if order.type != OrderType.MARKET:
                rejected.append(order)
                continue

            # Apply slippage: buyers get worse prices, sellers get worse prices.
            slippage = (self.slippage_bps / 10_000.0)
            if order.side == OrderSide.BUY:
                exec_price = bar.close * (1.0 + slippage)
            else:
                exec_price = bar.close * (1.0 - slippage)

            notional = exec_price * order.quantity
            fee = abs(notional) * self.fee_rate

            fills.append(
                Fill(
                    symbol=order.symbol,
                    side=order.side,
                    quantity=order.quantity,
                    price=exec_price,
                    fee=fee,
                    ts=market.ts if isinstance(market.ts, dt.datetime) else dt.datetime.now(dt.timezone.utc),
                    order_id=str(uuid.uuid4()),
                    client_order_id=order.client_order_id,
                )
            )

        return ExecutionReport(fills=fills, rejected_orders=rejected)


__all__ = ["ExecutionEngine", "NaiveBarExecutionEngine"]
