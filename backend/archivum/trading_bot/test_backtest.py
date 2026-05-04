import datetime as dt
import unittest

from archivum.trading_bot.backtest import BacktestRunner
from archivum.trading_bot.execution import NaiveBarExecutionEngine
from archivum.trading_bot.types import (
    MarketBar,
    MarketSnapshot,
    OrderRequest,
    OrderSide,
    ProposedOrders,
)


class BuyOnceStrategy:
    def __init__(self, symbol: str, quantity: float = 1.0):
        self.symbol = symbol
        self.quantity = quantity
        self._did = False

    def propose(self, state, market, *, rng=None):
        if self._did:
            return ProposedOrders(orders=[], metadata={})
        self._did = True
        return ProposedOrders(
            orders=[
                OrderRequest(symbol=self.symbol, side=OrderSide.BUY, quantity=self.quantity)
            ],
            metadata={},
        )


class ProposeMissingSymbolStrategy:
    def __init__(self, symbol: str):
        self.symbol = symbol
        self._done = False

    def propose(self, state, market, *, rng=None):
        if self._done:
            return ProposedOrders(orders=[], metadata={})
        self._done = True
        return ProposedOrders(orders=[OrderRequest(symbol=self.symbol, side=OrderSide.BUY, quantity=1.0)], metadata={})


class TestTradingBotFramework(unittest.TestCase):
    def test_backtest_executes_buy_at_close(self):
        t0 = dt.datetime(2026, 1, 1, tzinfo=dt.timezone.utc)
        t1 = t0 + dt.timedelta(minutes=1)

        snapshots = [
            MarketSnapshot(ts=t0, bars={"BTC": MarketBar(ts=t0, symbol="BTC", open=100, high=100, low=100, close=100)}),
            MarketSnapshot(ts=t1, bars={"BTC": MarketBar(ts=t1, symbol="BTC", open=110, high=110, low=110, close=110)}),
        ]

        runner = BacktestRunner(
            strategy=BuyOnceStrategy("BTC", quantity=1.0),
            execution_engine=NaiveBarExecutionEngine(fee_rate=0.0, slippage_bps=0.0),
            start_cash=1000.0,
            symbols=["BTC"],
        )

        result = runner.run(snapshots)
        self.assertEqual(len(result.fills), 1)
        self.assertAlmostEqual(result.fills[0].price, 100.0)
        self.assertAlmostEqual(result.end_positions["BTC"], 1.0)
        self.assertAlmostEqual(result.end_equity, 1010.0)
        self.assertAlmostEqual(result.total_return, 0.01)

    def test_rejects_orders_for_symbols_not_in_market_snapshot(self):
        t0 = dt.datetime(2026, 1, 1, tzinfo=dt.timezone.utc)

        snapshots = [
            MarketSnapshot(ts=t0, bars={"BTC": MarketBar(ts=t0, symbol="BTC", open=100, high=100, low=100, close=100)}),
        ]

        runner = BacktestRunner(
            strategy=ProposeMissingSymbolStrategy("ETH"),
            execution_engine=NaiveBarExecutionEngine(fee_rate=0.0, slippage_bps=0.0),
            start_cash=1000.0,
            symbols=["BTC"],
        )

        result = runner.run(snapshots)
        self.assertEqual(len(result.fills), 0)
        self.assertEqual(result.rejected_orders_count, 1)
        self.assertAlmostEqual(result.end_cash, 1000.0)
        self.assertAlmostEqual(result.end_equity, 1000.0)


if __name__ == "__main__":
    unittest.main()
