from example.algorithm import IntraDay
from example.binance import (
    BinanceAggTradesDecoder,
    BinanceFuturesREST,
    BinanceOrderEncoder,
    BinanceUserStreamDecoder,
)
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
                ),
                lot_size="0.001",
                backtest_start_date="2026-01-01",
                backtest_end_date="2026-01-01",
            ),
            Live(
                leverage=20,
                connector=Connector(
                    base_rest_url="https://demo-fapi.binance.com",
                    market_data_stream_url="wss://demo-fstream.binance.com/market/ws/dashusdt@aggTrade",
                    user_data_stream_url="wss://demo-fstream.binance.com/ws/",
                    order_stream_url="wss://testnet.binancefuture.com/ws-fapi/v1",
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
                timeframe=tf.M1, step_tick=5, state=True, ctrade=True
            ),
            risk_management=RiskManagement(
                max_lock_balance=pct(10.0),
                max_loss_balance=pct(10.0),
                entry_qty=pct(0.5),
                tp_dev=pct(1.0),
                sl_dev=pct(1.0),
                pass_signal_if_analysis_time_big=50_000,
                pass_execute_signal_if_timer_ms_exepired=1000,
            ),
        ),
        execution=HedgeExecution,
        with_execution=True,
    )
    imp.run_core()
    imp.run_vis()
