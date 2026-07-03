from src.setup import RunMode, Timeframe, download_data, run

if __name__ == "__main__":
    download_data("DASHUSDT", 2026, 1, 1, 2026, 1, 1)
    kwargs = run(
        run_mode=RunMode.Backtesting,
        timeframe=Timeframe._5M,
        symbol="DASHUSDT",
        laverage=20,
        max_loss_balance=0.1,
        max_lock_balance=0.05,
        entry_quantity=0.005,
        take_profit_deviation=0.05,
        stop_loss_deviation=0.05,
        sim_balance=5000.0,
        sim_taker_commission=0.005,
        sim_maker_commission=0.002,
        sim_min_order_size=5,
        sim_tick_size="0.01",
        sim_lot_size="0.001",
        backtest_start_date="2026-01-01",
        backtest_end_date="2026-01-01",
        save_orders_history=False,
        save_footprint_headers=False,
        save_algorithm_metadata=False,
    )
