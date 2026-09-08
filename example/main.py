from example.algorithm import IntraDay
from example.binance.agg_trades_decoder import BinanceAggTradesDecoder
from example.binance.order_encoder import BinanceOrderEncoder
from example.binance.user_stream_decoder import BinanceUserStreamDecoder
from example.execution import HedgeExecution
from imprint.api.setup import (
    Account,
    Backtest,
    Connector,
    Footprint,
    Imprint,
    Live,
    RiskManagement,
    Strategy,
    Timeframe,
    pct,
)

if __name__ == "__main__":
    imp = Imprint(
        run_mode=(
            Backtest,
            Backtest(
                account=Account(
                    leverage=50,
                    balance=5000,
                    min_order_size=5,
                    taker_commission=pct(0.05),
                    maker_commission=pct(0.02),
                    slippage=pct(0.05),
                    latency_ms=100,
                    scale_prec=15,
                    active_order_limit=1000,
                    save_orders_history=True,
                ),
                tick_size="0.01",
                lot_size="0.001",
                backtest_start_date="2026-01-01",
                backtest_end_date="2026-01-07",
            ),
            Live(
                connector=Connector(
                    base_uri_for_rest="https://fapi.binance.com",
                    base_uri_for_ws="wss://ws-fapi.binance.com/ws-fapi/v1",
                    base_uri_for_wss="wss://fstream.binance.com",
                    market_data_uri_for_wss="wss://fstream.binance.com/market/ws/dashusdt@aggTrade",
                ),
                agg_trades_decoder=BinanceAggTradesDecoder,
                order_encoder=BinanceOrderEncoder,
                user_stream_decoder=BinanceUserStreamDecoder,
            ),
        ),
        symbol="DASHUSDT",
        strategy=Strategy(
            algorithm=IntraDay,
            footprint=Footprint(
                timeframe=Timeframe.M5,
                step_tick=5,
                save_fp_headers=True,
            ),
            risk_management=RiskManagement(
                max_lock_balance=pct(10.0),
                max_loss_balance=pct(10.0),
                entry_qty=pct(0.5),
                tp_dev=pct(2.0),
                sl_dev=pct(1.8),
                pass_signal_if_analysis_time_big=50_000,
                pass_execute_signal_if_timer_ms_exepired=1000,
            ),
        ),
        execution=HedgeExecution,
        with_execution=True,
    )
    imp.run_core()
    imp.run_vis()
