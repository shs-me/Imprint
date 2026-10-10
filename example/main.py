import imprint
from example.algorithm import IntraDay
from example.execution import HedgeExecution
from imprint import pct, tf


def live():
    imp = imprint.live(symbol="DASHUSDT", leverage=20, with_execution=True)
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
        pass_signal_if_analysis_time_big=50_000,
        pass_execute_signal_if_timer_ms_exepired=1000,
    )
    imp.build()
    imp.engine.run_core()


def backtest():
    imp = imprint.backtest(
        symbols=["DASHUSDT"],
        tick_size=["0.01"],
        lot_size=["0.001"],
        start_date=["2026-01-01"],
        end_date=["2026-01-01"],
        with_execution=True,
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
        tp_dev=[
            pct(1.0),
            pct(2.0),
            pct(4.0),
        ],
        sl_dev=[
            pct(2.0),
            pct(1.7),
            pct(3.7),
        ],
        pass_signal_if_analysis_time_big=[50_000],
        pass_execute_signal_if_timer_ms_exepired=[1000],
    )
    imp.footprint(
        timeframe=[tf.M1],
        step_tick=[5],
        state=[True],
        ctrade=[True],
    )
    imp.strategy(
        algorithm=[IntraDay],
        execution=[HedgeExecution],
    )
    imp.build()
    imp.engine.run_vis(auto_open=False)


if __name__ == "__main__":
    imp = backtest()
