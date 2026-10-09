from dataclasses import dataclass, field
from typing import final, override

from loguru import logger

import imprint.configs as cfg
from imprint._boot.base import Base, InitFailed
from imprint._core.configs import Account, Coin, MarketDataStream, Setup
from imprint._core.utils.base_adapters import ApiNotFoundError


@dataclass(slots=True)
class Live(Base):
    """Manage live trading session initialization, REST exchange connectivity, and account synchronization.

    Parameters
    ----------
    run_mode : imprint.configs.Live
        Live trading configuration containing exchange REST client, decoders, encoders, and leverage settings.

    Attributes
    ----------
    run_mode : imprint.configs.Live
        Live trading configuration parameters.
    """

    run_mode: cfg.Live

    _coin: Coin = field(init=False)
    _account: Account = field(init=False)

    _rest: cfg.ExchangeREST = field(init=False)

    @override
    def _post_init(self) -> None:
        _ = self.run_mode
        # - - -
        self._segments.append(MarketDataStream(count_reader=1))

        self._other_configs.append([_.connector])

        self.prepare_coin_config()
        self._other_configs.append([self._coin])

        self.prepare_account_config()
        self._other_configs.append([self._account])

    @override
    def prepare_setup_config(self) -> None:
        _ = self.run_mode
        # - - -
        Base.prepare_setup_config(self)

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

    def prepare_coin_config(self) -> None:
        _ = self.run_mode
        # - - -
        self._coin = Coin(symbol=_.symbol)

        self._rest = _.exchange_rest(logger=logger, symbol=self._coin.symbol)
        self._rest.base_url = _.connector.base_rest_url

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

    def prepare_account_config(self) -> None:
        self._account = Account(leverage=self.run_mode.leverage)

        self._account.min_order_size = self._rest.min_order_size
        if not self._account.min_order_size:
            raise InitFailed(
                f"Init, failed. Min order size({self._account.min_order_size}) is not valid"
            )
        else:
            logger.info(
                f"Min nominal order size: {self._account.min_order_size}"
            )

        if self.with_execution:
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
