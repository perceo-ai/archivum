from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import Dict, Iterable, List, Mapping, MutableMapping, Optional, Sequence

from .execution import ExecutionEngine
from .types import BacktestResult, Fill, MarketSnapshot, OrderSide, PortfolioState, ProposedOrders
from .strategy import Strategy


def _apply_fill(state: PortfolioState, fill: Fill) -> None:
    if fill.side == OrderSide.BUY:
        state.cash -= fill.price * fill.quantity + fill.fee
        state.positions[fill.symbol] = state.positions.get(fill.symbol, 0.0) + fill.quantity
    else:
        state.cash += fill.price * fill.quantity - fill.fee
        state.positions[fill.symbol] = state.positions.get(fill.symbol, 0.0) - fill.quantity


@dataclass
class BacktestRunner:
    strategy: Strategy
    execution_engine: ExecutionEngine
    start_cash: float = 10_000.0
    fee_rate: float = 0.0  # informational; engine may also model fees
    symbols: Optional[Sequence[str]] = None

    def run(self, snapshots: Iterable[MarketSnapshot], *, notes: Optional[str] = None) -> BacktestResult:
        snapshots_list = list(snapshots)
        if not snapshots_list:
            raise ValueError("Backtest requires at least one MarketSnapshot")

        # Initialize portfolio.
        symbols = list(self.symbols) if self.symbols is not None else sorted(
            {sym for snap in snapshots_list for sym in snap.bars.keys()}
        )
        state = PortfolioState(cash=self.start_cash, positions={sym: 0.0 for sym in symbols})

        fills: List[Fill] = []
        rejected_orders_count = 0
        last_close: Dict[str, float] = {sym: 0.0 for sym in symbols}

        for snap in snapshots_list:
            for sym, bar in snap.bars.items():
                last_close[sym] = bar.close

            proposed: ProposedOrders = self.strategy.propose(state, snap)
            exec_report = self.execution_engine.execute(proposed.orders, snap)

            rejected_orders_count += len(exec_report.rejected_orders)
            for fill in exec_report.fills:
                _apply_fill(state, fill)
                fills.append(fill)

        end_equity = state.cash + sum(state.positions.get(sym, 0.0) * last_close.get(sym, 0.0) for sym in symbols)
        total_return = (end_equity - self.start_cash) / self.start_cash if self.start_cash else 0.0

        return BacktestResult(
            start_cash=self.start_cash,
            end_cash=state.cash,
            end_positions=dict(state.positions),
            end_equity=end_equity,
            total_return=total_return,
            fills=fills,
            rejected_orders_count=rejected_orders_count,
            notes=notes,
        )


__all__ = ["BacktestRunner"]
