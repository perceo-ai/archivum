from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Protocol

from .types import OrderRequest, OrderSide, OrderType, ProposedOrders


class CounselOutputParser(Protocol):
    """Parse an LLM-counsel output blob into proposed orders."""

    def parse(self, counsel_output: Mapping[str, Any]) -> ProposedOrders:  # pragma: no cover
        raise NotImplementedError


@dataclass(frozen=True)
class BasicCounselActionAdapter:
    """Best-effort adapter for an expected counsel shape.

    Expected (example) counsel payload:

    {
      "decision_trace": "...",
      "orders": [
        {"symbol": "BTC", "side": "buy", "quantity": 1.0, "type": "market"}
      ]
    }

    If your counsel output differs, swap in a custom parser.
    """

    decision_trace_key: str = "decision_trace"
    orders_key: str = "orders"

    def parse(self, counsel_output: Mapping[str, Any]) -> ProposedOrders:
        orders_raw = counsel_output.get(self.orders_key, [])
        if not isinstance(orders_raw, list):
            orders_raw = []

        parsed_orders: list[OrderRequest] = []
        for o in orders_raw:
            try:
                symbol = str(o["symbol"])
                side = OrderSide(str(o["side"]))
                quantity = float(o["quantity"])
                typ = OrderType(str(o.get("type", OrderType.MARKET.value)))
                parsed_orders.append(
                    OrderRequest(
                        symbol=symbol,
                        side=side,
                        quantity=quantity,
                        type=typ,
                        client_order_id=o.get("client_order_id"),
                    )
                )
            except Exception:
                # Contract-first: malformed items just get ignored.
                continue

        metadata = {
            self.decision_trace_key: counsel_output.get(self.decision_trace_key),
            "source": "llm_counsel_adapter",
        }
        return ProposedOrders(orders=parsed_orders, metadata=metadata)


__all__ = ["CounselOutputParser", "BasicCounselActionAdapter"]
