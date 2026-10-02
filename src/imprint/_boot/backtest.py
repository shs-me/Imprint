from dataclasses import dataclass, field
from typing import final, override

from loguru import logger

import imprint.configs as cfg
from imprint._boot.base import Base
from imprint._core.configs import MarketDataStream as _MDS
from imprint._core.constant import (
    EQUITY_HISTORY_DATA_PATH,
    FOOTPRINT_HEADERS_DATA_PATH,
    ORDERS_HISTORY_DATA_PATH,
)
from imprint._core.utils import DownloadAggTradesHistory
from imprint._core.utils.agg_trades_history_downloader import DownloadError
from imprint._core.utils.exc_dumper import error_handler
from imprint._vis.main import Render


@dataclass(slots=True)
class Backtest(Base):
    run_mode: cfg.Backtest

    _prefix_core_log_format: str = field(default="{elapsed} ", init=False)

    @override
    def _post_init(self) -> bool:
        self._args.append(
            _MDS(
                data_size=32,
                cast_to_int64=True,
                count_reader=2 if self.with_execution else 1,
            )
        )

        self._setup_core.backtest_start_date = self.run_mode.backtest_start_date
        self._setup_core.backtest_end_date = self.run_mode.backtest_end_date
        self._setup_core.backtesting = True

        self._account: cfg.Account = self.run_mode.account

        self._coin.tick_size = self.run_mode.tick_size
        self._coin.lot_size = self.run_mode.lot_size

        try:
            DownloadAggTradesHistory(
                logger=logger,
                symbol=self.symbol,
                start_date_str=self.run_mode.backtest_start_date,
                end_date_str=self.run_mode.backtest_end_date,
                price_mult=self._coin.price_mult,
                qty_mult=self._coin.qty_mult,
            ).download()

        except DownloadError as e:
            logger.error(f"Init data, failed: {e}")
            return False

        return True

    @error_handler()
    def run_vis(self, auto_open: bool = True) -> None:
        if self._init_complete and self.with_execution:
            logger.info("Visualization, started.")
            Render(
                footprint_headers_path=FOOTPRINT_HEADERS_DATA_PATH,
                symbol=self._coin.symbol,
                start_date_str=self.run_mode.backtest_start_date,
                end_date_str=self.run_mode.backtest_end_date,
                equity_history_path=EQUITY_HISTORY_DATA_PATH,
                orders_history_path=ORDERS_HISTORY_DATA_PATH,
                start_balance=self.run_mode.account.balance,
                price_mult=self._coin.price_mult,
                qty_mult=self._coin.qty_mult,
                scale_mult=self.run_mode.account.scale_mult,
                leverage=self.run_mode.account.leverage,
                timeframe=self.strategy.footprint.timeframe,
                auto_open=auto_open,
            )
            logger.info("Visualization, closed.\n")


@final
@dataclass(slots=True)
class BacktestEngine(Backtest): ...  # pyright: ignore[reportUninitializedInstanceVariable]
