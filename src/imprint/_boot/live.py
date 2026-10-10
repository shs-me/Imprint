"""Provide live trading engine orchestration, exchange REST validation, and builder interfaces."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import final, override

from loguru import logger

from imprint._boot.base import Base, BoundFactory, EngineNotBuilded, InitFailed
from imprint._boot.configs import Adapters
from imprint._core.configs import (
    Account,
    Coin,
    Connector,
    Footprint,
    MarketDataStream,
    RiskManagement,
    Setup,
)
from imprint._core.footprint import StrategyEngine
from imprint._core.pipeline.executing import ExecutionEngine
from imprint._core.utils import ExchangeREST
from imprint._core.utils.base_adapters import ApiNotFoundError


@dataclass(slots=True)
class Live(Base):
    """Manage live trading session initialization, exchange connectivity, coin validation, and balance checks.

    Parameters
    ----------
    _symbol : str
        Target trading symbol for live connectivity.
    _leverage : int
        Account leverage multiplier to set on the exchange.
    _adapters : Adapters
        Protocol adapters configuration for REST, WebSockets, and encoding.
    _connector : Connector
        Network connector configuration for exchange endpoints.

    Attributes
    ----------
    _coin : Coin
        Configured coin metadata and specification.
    _account : Account
        Configured account state and leverage properties.
    _rest : ExchangeREST
        Instantiated exchange REST client adapter.
    """

    _symbol: str
    _leverage: int
    _adapters: Adapters
    _connector: Connector

    _coin: Coin = field(init=False)
    _account: Account = field(init=False)
    _rest: ExchangeREST = field(init=False)

    @override
    def _post_init(self) -> None:
        """Initialize shared memory, prepare coin specifications, and configure live account state."""
        self._segments.append(MarketDataStream(count_reader=1))

        self._other_configs.append([self._connector])

        self._prepare_coin_config()
        self._other_configs.append([self._coin])

        self._prepare_account_config()
        self._other_configs.append([self._account])

    @override
    def _prepare_setup_config(self) -> None:
        """Construct setup configurations with live exchange REST, WebSocket, and encoding module paths."""
        _ = self._adapters
        # - - -
        Base._prepare_setup_config(self)

        setup: Setup = self._setups[0]
        setup.agg_trades_decoder_module = _.agg_trades_decoder.__module__
        setup.agg_trades_decoder_class_name = _.agg_trades_decoder.__name__
        setup.user_stream_decoder_module = _.user_stream_decoder.__module__
        setup.user_stream_decoder_class_name = _.user_stream_decoder.__name__
        setup.order_encoder_module = _.order_encoder.__module__
        setup.order_encoder_class_name = _.order_encoder.__name__
        setup.exchange_rest_module = _.exchange_rest.__module__
        setup.exchange_rest_class_name = _.exchange_rest.__name__
        setup.backtesting = False

    def _prepare_coin_config(self) -> None:
        """Fetch and validate tick size and lot size market metadata from exchange REST API."""
        self._coin = Coin(symbol=self._symbol)

        self._rest = self._adapters.exchange_rest(
            logger=logger, symbol=self._coin.symbol
        )
        self._rest.base_url = self._connector.base_rest_url

        self._coin.tick_size = self._rest.tick_size
        if not self._coin.tick_size:
            raise InitFailed(
                f"Init, failed. Tick size({self._coin.tick_size}) is not valid"
            )
        else:
            logger.info(f"Tick size: {self._coin.tick_size}")

        self._coin.lot_size = self._rest.lot_size
        if not self._coin.lot_size:
            raise InitFailed(
                f"Init, failed. Lot size({self._coin.lot_size}) is not valid"
            )
        else:
            logger.info(f"Lot size: {self._coin.lot_size}")

    def _prepare_account_config(self) -> None:
        """Validate minimum order size, configure exchange leverage, and fetch remote account balance."""
        self._account = Account(leverage=self._leverage)

        self._account.min_order_size = self._rest.min_order_size
        if not self._account.min_order_size:
            raise InitFailed(
                f"Init, failed. Min order size({self._account.min_order_size}) is not valid"
            )
        else:
            logger.info(
                f"Min nominal order size: {self._account.min_order_size}"
            )

        if self._with_execution:
            try:
                self._rest.set_leverage(self._account.leverage)
                logger.info(f"Leverage: {self._account.leverage}")
                self._account.balance = self._rest.get_balance()
                if not self._account.balance:
                    raise InitFailed(
                        f"Init, failed. Balance({self._account.balance}) is not valid"
                    )
                else:
                    logger.info(f"Balance: {self._account.balance}")

            except ApiNotFoundError as exc:
                raise InitFailed("API/SECRET key doest exists in env") from exc


@final
@dataclass(slots=True)
class LiveEngine(Live):  # pyright: ignore[reportUninitializedInstanceVariable]
    """Concrete live trading engine instance."""


@final
@dataclass(slots=True)
class LiveBuilder:
    """Fluent builder for configuring and instantiating live trading engines.

    Parameters
    ----------
    symbol : str
        Target trading symbol.
    leverage : int
        Account leverage multiplier.
    with_execution : bool
        Whether to enable live order execution and remote balance fetching.

    Attributes
    ----------
    _adapters : Adapters
        Configured protocol adapters.
    _connector : Connector
        Configured network connector.
    _footprint : Footprint
        Configured footprint parameters.
    _risk_management : RiskManagement
        Configured risk management rules.
    _algorithm : type[StrategyEngine]
        Configured strategy algorithm class.
    _execution : type[ExecutionEngine]
        Configured execution engine class.
    _engine : LiveEngine | None
        Instantiated live engine, or None if not yet built.
    """

    symbol: str
    leverage: int
    with_execution: bool

    _adapters: Adapters = field(default_factory=lambda: Adapters(), init=False)
    _connector: Connector = field(
        default_factory=lambda: Connector(), init=False
    )
    _footprint: Footprint = field(
        default_factory=lambda: Footprint(), init=False
    )
    _risk_management: RiskManagement = field(
        default_factory=lambda: RiskManagement(), init=False
    )
    _algorithm: type[StrategyEngine] = field(init=False)
    _execution: type[ExecutionEngine] = field(init=False)
    _engine: LiveEngine | None = field(default=None, init=False)

    @property
    def adapters(self) -> type[Adapters]:
        """Bind and configure exchange protocol adapter classes.

        Returns
        -------
        BoundFactory
            Factory interface for setting protocol adapter attributes.
        """
        return BoundFactory(Adapters, self, "_adapters")  # pyright: ignore[ reportReturnType]

    @property
    def connector(self) -> type[Connector]:
        """Bind and configure exchange network endpoints and URLs.

        Returns
        -------
        BoundFactory
            Factory interface for setting connector attributes.
        """
        return BoundFactory(Connector, self, "_connector")  # pyright: ignore[ reportReturnType]

    @property
    def footprint(self) -> type[Footprint]:
        """Bind and configure live footprint aggregation parameters.

        Returns
        -------
        BoundFactory
            Factory interface for setting footprint attributes.
        """
        return BoundFactory(Footprint, self, "_footprint")  # pyright: ignore[ reportReturnType]

    @property
    def risk_management(self) -> type[RiskManagement]:
        """Bind and configure live risk management limits and execution timeouts.

        Returns
        -------
        BoundFactory
            Factory interface for setting risk management attributes.
        """
        return BoundFactory(RiskManagement, self, "_risk_management")  # pyright: ignore[ reportReturnType]

    def strategy(
        self, algorithm: type[StrategyEngine], execution: type[ExecutionEngine]
    ) -> LiveBuilder:
        """Assign the strategy algorithm and execution engine to the live builder.

        Parameters
        ----------
        algorithm : type[StrategyEngine]
            Strategy engine algorithm class.
        execution : type[ExecutionEngine]
            Execution engine class.

        Returns
        -------
        LiveBuilder
            The builder instance for method chaining.
        """
        self._algorithm = algorithm
        self._execution = execution
        return self

    def build(self) -> None:
        """Construct and initialize the live trading engine instance from accumulated configurations."""
        self._engine = LiveEngine(
            _algorithm=self._algorithm,
            _execution=self._execution,
            _footprint=self._footprint,
            _risk_management=self._risk_management,
            _with_execution=self.with_execution,
            _symbol=self.symbol,
            _leverage=self.leverage,
            _adapters=self._adapters,
            _connector=self._connector,
        )

    @property
    def engine(self) -> LiveEngine:
        """Retrieve the built live engine instance.

        Returns
        -------
        LiveEngine
            Configured live engine instance.

        Raises
        ------
        EngineNotBuilded
            If build() has not been called prior to accessing the engine.
        """
        if self._engine is not None:
            return self._engine
        else:
            raise EngineNotBuilded
