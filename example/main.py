from example.algorithm import IntraDay
from example.binance.agg_trades_decoder import BinanceAggTradesDecoder
from example.binance.order_encoder import BinanceOrderEncoder
from example.binance.rest_adapter import BinanceFuturesREST
from example.binance.user_stream_decoder import BinanceUserStreamDecoder
from example.execution import HedgeExecution
from imprint import Imprint, pct, tf
from imprint.configs import (
    Account,
    Backtest,
    Connector,
    Footprint,
    Live,
    RiskManagement,
    Strategy,
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
                    base_rest_url="https://fapi.binance.com",
                    base_ws_url="wss://ws-fapi.binance.com/ws-fapi/v1",
                    base_wss_url="wss://fstream.binance.com",
                    market_data_uri_for_wss="wss://fstream.binance.com/market/ws/dashusdt@aggTrade",
                    get_user_data_uri_for_wss="wss://fstream.binance.com/pm/v1/userSecure?listenKey=",
                ),
                agg_trades_decoder=BinanceAggTradesDecoder,
                order_encoder=BinanceOrderEncoder,
                user_stream_decoder=BinanceUserStreamDecoder,
                exchange_rest=BinanceFuturesREST,
            ),
        ),
        symbol="DASHUSDT",
        strategy=Strategy(
            algorithm=IntraDay,
            footprint=Footprint(
                timeframe=tf.M5,
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
