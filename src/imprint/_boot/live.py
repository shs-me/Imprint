from dataclasses import dataclass, field
from typing import final, override

from loguru import logger

import imprint.configs as cfg
from imprint._boot.base import Base, InitFailed
from imprint._core.configs import MarketDataStream as _MDS
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

    _account: cfg.Account = field(init=False)
    _rest: cfg.ExchangeREST = field(init=False)

    @override
    def _post_init(self) -> None:
        """Initialize live data streams, REST connection endpoints, exchange limits, leverage, and initial account balance.

        Returns
        -------
        bool
            True if all exchange connection checks, tick/lot sizes, and balances are successfully verified; False otherwise.

        Raises
        ------
        ApiNotFoundError
            Caught internally if API or secret keys are missing from environment variables during execution mode.
        """
        _ = self.run_mode
        # - - -
        self._segments.append(_MDS(count_reader=1))
        self._other_configs.append([_.connector])
        self._account = cfg.Account(leverage=_.leverage)
        self._other_configs.append([self._account])

        setup = self._setups[0]
        setup.agg_trades_decoder_module = _.agg_trades_decoder.__module__
        setup.agg_trades_decoder_class_name = _.agg_trades_decoder.__name__
        setup.user_stream_decoder_module = _.user_stream_decoder.__module__
        setup.user_stream_decoder_class_name = _.user_stream_decoder.__name__
        setup.order_encoder_module = _.order_encoder.__module__
        setup.order_encoder_class_name = _.order_encoder.__name__
        setup.exchange_rest_module = _.exchange_rest.__module__
        setup.exchange_rest_class_name = _.exchange_rest.__name__
        setup.backtesting = False

        coin = self._coins[0]
        self._rest = _.exchange_rest(logger=logger, symbol=coin.symbol)
        self._rest.base_url = _.connector.base_rest_url

        coin.tick_size = self._rest.tick_size
        if not coin.tick_size:
            raise InitFailed(
                f"Init, failed. Tick size({coin.tick_size}) is not valid"
            )
        else:
            logger.info(f"Tick size: {coin.tick_size}")

        coin.lot_size = self._rest.lot_size
        if not coin.lot_size:
            raise InitFailed(
                f"Init, failed. Lot size({coin.lot_size}) is not valid"
            )
        else:
            logger.info(f"Lot size: {coin.lot_size}")

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
