"""Trading bot framework (execution + backtesting + strategy contracts).

This package is intentionally lightweight: it provides interface contracts and a
naive reference implementation suitable for wiring into an LLM-counsel flow.
"""

from .types import (
    OrderSide,
    OrderType,
    OrderRequest,
    Fill,
    ExecutionReport,
    MarketBar,
    MarketSnapshot,
    PortfolioState,
    ProposedOrders,
    BacktestResult,
)
from .strategy import Strategy
from .execution import ExecutionEngine, NaiveBarExecutionEngine
from .backtest import BacktestRunner

__all__ = [
    "OrderSide",
    "OrderType",
    "OrderRequest",
    "Fill",
    "ExecutionReport",
    "MarketBar",
    "MarketSnapshot",
    "PortfolioState",
    "ProposedOrders",
    "BacktestResult",
    "Strategy",
    "ExecutionEngine",
    "NaiveBarExecutionEngine",
    "BacktestRunner",
]
