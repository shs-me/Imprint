from example.algorithm import IntraDay
from example.binance.agg_trades_decoder import BinanceAggTradesDecoder
from example.binance.order_encoder import BinanceOrderEncoder
from example.binance.user_stream_decoder import BinanceUserStreamDecoder
from example.execution import HedgeExecution
from imprint.api import Percent, Timeframe, run
from imprint.api.configs import (
    Account,
    Backtesting,
    Connector,
    Footprint,
    Real,
    RiskManagment,
    SetupCore,
    Strategy,
    Visualization,
)


def run_backtest():
    main(
        Backtesting(
            account=Account(
                leverage=50,
                balance=5000,
                min_order_size=5,
                taker_commission=Percent("0.05%"),
                maker_commission=Percent("0.02%"),
                slippage=Percent("0.05%"),
                latency_ms=100,
                scale_prec=15,
                active_order_limit=1000,
                save_orders_history=True,
            ),
            tick_size="0.01",
            lot_size="0.001",
            backtest_start_date="2026-01-01",
            backtest_end_date="2026-01-07",
            with_visualization=Visualization(
                only_visualization=False,
                render_to_html=True,
            ),
        )
    )


def run_live():
    main(
        Real(
            connector=Connector(
                base_uri_for_rest="https://fapi.binance.com",
                base_uri_for_ws="wss://ws-fapi.binance.com/ws-fapi/v1",
                base_uri_for_wss="wss://fstream.binance.com",
                market_data_uri_for_wss="wss://fstream.binance.com/market/ws/dashusdt@aggTrade",
            ),
            agg_trades_decoder=BinanceAggTradesDecoder,
            order_encoder=BinanceOrderEncoder,
            user_stream_decoder=BinanceUserStreamDecoder,
        )
    )


def main(run_mode: Backtesting | Real):
    run(
        SetupCore(
            run_mode=run_mode,
            strategy=Strategy(
                algorithm=IntraDay,
                footprint=Footprint(
                    timeframe=Timeframe.M5,
                    step_tick=5,
                    save_fp_headers=True,
                ),
                risk_managment=RiskManagment(
                    max_lock_balance=Percent("10%"),
                    max_loss_balance=Percent("10%"),
                    entry_qty=Percent("0.5%"),
                    tp_dev=Percent("2%"),
                    sl_dev=Percent("1.8%"),
                    pass_signal_if_analysis_time_big=50_000,
                    pass_execute_signal_if_timer_ms_exepired=1000,
                ),
            ),
            symbol="DASHUSDT",
            with_execution=HedgeExecution,
        )
    )


if __name__ == "__main__":
    run_backtest()
