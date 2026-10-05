from dataclasses import dataclass, field
from typing import final, override

from loguru import logger

import imprint.configs as cfg
from imprint._boot.base import Base
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

    _prefix_core_log_format: str = field(default="", init=False)
    _rest: cfg.ExchangeREST = field(init=False)

    @override
    def _post_init(self) -> bool:
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
        self._args.append(_MDS(count_reader=1))
        self._args.append(self.run_mode.connector)

        self._setup_core.agg_trades_decoder_module = (
            self.run_mode.agg_trades_decoder.__module__
        )
        self._setup_core.agg_trades_decoder_class_name = (
            self.run_mode.agg_trades_decoder.__name__
        )
        self._setup_core.user_stream_decoder_module = (
            self.run_mode.user_stream_decoder.__module__
        )
        self._setup_core.user_stream_decoder_class_name = (
            self.run_mode.user_stream_decoder.__name__
        )
        self._setup_core.order_encoder_module = (
            self.run_mode.order_encoder.__module__
        )
        self._setup_core.order_encoder_class_name = (
            self.run_mode.order_encoder.__name__
        )
        self._setup_core.exchange_rest_module = (
            self.run_mode.exchange_rest.__module__
        )
        self._setup_core.exchange_rest_class_name = (
            self.run_mode.exchange_rest.__name__
        )
        self._setup_core.backtesting = False

        self._account: cfg.Account = cfg.Account(
            leverage=self.run_mode.leverage
        )

        self._rest = self.run_mode.exchange_rest(
            logger=logger, symbol=self.symbol
        )
        self._rest.base_url = self.run_mode.connector.base_rest_url

        self._coin.tick_size = self._rest.tick_size
        if not self._coin.tick_size:
            logger.error(
                f"Init data, failed. Tick size({self._coin.tick_size}) is not valid"
            )
            return False
        else:
            logger.info(f"Tick size: {self._coin.tick_size}")

        self._coin.lot_size = self._rest.lot_size
        if not self._coin.lot_size:
            logger.error(
                f"Init data, failed. Lot size({self._coin.lot_size}) is not valid"
            )
            return False
        else:
            logger.info(f"Lot size: {self._coin.lot_size}")

        self._account.min_order_size = self._rest.min_order_size
        if not self._account.min_order_size:
            logger.error(
                f"Init data, failed. Min order size({self._account.min_order_size}) is not valid"
            )
            return False
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
                    logger.error(
                        f"Init data, failed. Balance({self._account.balance}) is not valid"
                    )
                    return False
                else:
                    logger.info(f"Balance: {self._account.balance}")

            except ApiNotFoundError:
                logger.error("API/SECRET key doest exists in env")
                return False

        return True


@final
@dataclass(slots=True)
class LiveEngine(Live):  # pyright: ignore[reportUninitializedInstanceVariable]
    """Concrete live trading engine instance."""
