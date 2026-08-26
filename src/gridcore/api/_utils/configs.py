from dataclasses import dataclass

from ...core.configs import (
    Account,
    Coin,
    Configuration,
    Connector,
    Footprint,
    RiskManagment,
    Setup,
)
from ...core.footprint import FootprintEngine
from ...core.pipeline.executing import BaseExecution
from ...core.pipeline.utils.base_adapters import (
    AggTrades,
    OrderEncoder,
    UserStreamDecoder,
)

__all__ = [
    "Visualization",
    "Backtesting",
    "Real",
    "Account",
    "Connector",
    "Footprint",
    "RiskManagment",
    "Strategy",
]


@dataclass
class Visualization:
    only_visualization: bool = False


@dataclass
class Backtesting:
    account: Account
    tick_size: str = "0.01"
    lot_size: str = "0.001"
    backtest_start_date: str = "2026-01-01"
    backtest_end_date: str = "2026-01-01"
    with_visualization: Visualization | None = None


@dataclass
class Real:
    connector: Connector
    agg_trade_struct: type[AggTrades]
    user_stream_decoder: type[UserStreamDecoder]
    order_encoder: type[OrderEncoder]


@dataclass
class Strategy:
    algorithm: type[FootprintEngine]
    footprint: Footprint
    risk_managment: RiskManagment


@dataclass
class SetupCore:
    run_mode: Backtesting | Real
    strategy: Strategy
    symbol: str = "DASHUSDT"
    with_execution: type[BaseExecution] | None = None

    def __post_init__(self) -> None:
        args: list[Configuration] = [
            self.strategy.risk_managment,
            self.strategy.footprint,
        ]
        self.coin: Coin = Coin(symbol=self.symbol)
        self.setup: Setup = Setup(
            algorithm_module=self.strategy.algorithm.__module__,
            algorithm_class_name=self.strategy.algorithm.__name__,
        )

        if isinstance(self.run_mode, Backtesting):
            self.setup.backtest_start_date = self.run_mode.backtest_start_date
            self.setup.backtest_end_date = self.run_mode.backtest_end_date
            self.setup.backtesting = True

            self.coin.tick_size = self.run_mode.tick_size
            self.coin.lot_size = self.run_mode.lot_size

            args.append(self.coin)
            args.append(self.run_mode.account)

        else:
            self.setup.agg_trades_struct_module = (
                self.run_mode.agg_trade_struct.__module__
            )
            self.setup.agg_trades_struct_class_name = (
                self.run_mode.agg_trade_struct.__name__
            )
            self.setup.user_stream_decoder_module = (
                self.run_mode.user_stream_decoder.__module__
            )
            self.setup.user_stream_decoder_class_name = (
                self.run_mode.user_stream_decoder.__name__
            )
            self.setup.order_encoder_module = self.run_mode.order_encoder.__module__
            self.setup.order_encoder_class_name = self.run_mode.order_encoder.__name__

            self.setup.backtesting = False

            args.append(self.coin)
            args.append(self.run_mode.connector)

        if self.with_execution is not None:
            self.setup.execution = True
            self.setup.execution_module = self.with_execution.__module__
            self.setup.execution_class_name = self.with_execution.__name__
        else:
            self.setup.execution = False

        args.append(self.setup)

        self.args: tuple[Configuration, ...] = tuple(args)
