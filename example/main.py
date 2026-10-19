from datetime import date, timedelta

import imprint
from example.algorithm import IntraDay
from example.execution import HedgeExecution
from imprint import pct, tf


def live():
    imp = imprint.live(
        symbol="DASHUSDT",
        leverage=20,
        with_execution=True,
        pass_debug_logs=False,
    )
    imp.connector(
        base_rest_url="https://demo-fapi.binance.com",
        market_data_stream_url="wss://demo-fstream.binance.com/market/ws/dashusdt@aggTrade",
        user_data_stream_url="wss://demo-fstream.binance.com/ws/",
        order_stream_url="wss://testnet.binancefuture.com/ws-fapi/v1",
    )
    imp.strategy(algorithm=IntraDay, execution=HedgeExecution)
    imp.footprint(timeframe=tf.M1, step_tick=5, state=True, ctrade=True)
    imp.risk_management(
        max_lock_balance=pct(10.0),
        max_loss_balance=pct(10.0),
        entry_qty=pct(0.5),
        tp_dev=pct(1.0),
        sl_dev=pct(1.0),
        pass_signal_time=60_000,
        expiration_signal_time=1000,
    )
    imp.build()
    imp.engine.run_core()


def gen_date(
    base_date: date | str, with_base_date: bool, step: int, count: int
) -> list[str]:
    if isinstance(base_date, date):
        dates: list[str] = [base_date.isoformat()] if with_base_date else []
        start_date: date = base_date
    else:
        dates = [base_date] if with_base_date else []
        start_date = date.fromisoformat(base_date)

    for _ in range(count):
        dates.append(
            (start_date := (start_date + timedelta(days=step))).isoformat()
        )
    return dates


def backtest():
    imp = imprint.backtest(
        symbols=["DASHUSDT"],
        tick_size=["0.01"],
        lot_size=["0.001"],
        start_date=gen_date("2026-01-01", True, 1, 14),
        end_date=gen_date("2026-01-01", True, 1, 14),
        with_execution=True,
        pass_debug_logs=False,
    )
    imp.account(
        leverage=[50],
        balance=[5000.0],
        min_order_size=[5.0],
        taker_commission=[pct(0.05)],
        maker_commission=[pct(0.02)],
        slippage=[pct(0.05)],
        latency_ms=[100],
        scale_prec=[8],
        active_order_limit=[1000],
    )
    imp.risk_management(
        max_lock_balance=[pct(10.0)],
        max_loss_balance=[pct(10.0)],
        entry_qty=[pct(0.5)],
        tp_dev=[pct(2.0)],
        sl_dev=[pct(1.7)],
        pass_signal_time=[60_000],
        expiration_signal_time=[1000],
    )
    imp.footprint(
        timeframe=[tf.M5],
        step_tick=[5],
        state=[True],
        ctrade=[True],
    )
    imp.strategy(
        algorithm=[IntraDay],
        execution=[HedgeExecution],
    )
    imp.build()
    imp.engine.run_vis()


if __name__ == "__main__":
    imp = backtest()
