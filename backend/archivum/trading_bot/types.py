from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Mapping, Optional


class OrderSide(str, Enum):
    BUY = "buy"
    SELL = "sell"


class OrderType(str, Enum):
    MARKET = "market"


@dataclass(frozen=True)
class OrderRequest:
    symbol: str
    side: OrderSide
    quantity: float
    type: OrderType = OrderType.MARKET
    client_order_id: Optional[str] = None


@dataclass(frozen=True)
class Fill:
    symbol: str
    side: OrderSide
    quantity: float
    price: float
    fee: float
    ts: dt.datetime
    order_id: str
    client_order_id: Optional[str] = None


@dataclass(frozen=True)
class ExecutionReport:
    fills: List[Fill] = field(default_factory=list)
    rejected_orders: List[OrderRequest] = field(default_factory=list)


@dataclass(frozen=True)
class MarketBar:
    ts: dt.datetime
    symbol: str
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0


@dataclass(frozen=True)
class MarketSnapshot:
    """All tradable bars at a single timestamp.

    Backtests that do not require cross-asset timing can supply a snapshot
    containing one bar per step.
    """

    ts: dt.datetime
    bars: Mapping[str, MarketBar]


@dataclass
class PortfolioState:
    cash: float
    positions: Dict[str, float] = field(default_factory=dict)  # symbol -> qty


@dataclass(frozen=True)
class ProposedOrders:
    orders: List[OrderRequest]
    # Free-form context for logging, debugging, and LLM traceability.
    metadata: Mapping[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class BacktestResult:
    start_cash: float
    end_cash: float
    end_positions: Mapping[str, float]
    end_equity: float
    total_return: float
    fills: List[Fill]
    rejected_orders_count: int
    # Optional strategy/execution debug.
    notes: Optional[str] = None
