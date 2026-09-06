"""Unit tests for `imprint.core.exchange.account.position`."""

from unittest.mock import MagicMock

from imprint.core import constant as c
from imprint.core.configs import Account, Coin, pct
from imprint.core.exchange.account.converter import (
    to_long_nPnl,
    to_nMargin,
    to_short_nPnl,
)
from imprint.core.exchange.account.position import (
    Position,
    _update_long_mae_and_mfe,
    _update_long_position,
    _update_long_unrealized_nPnl,
    _update_short_mae_and_mfe,
    _update_short_position,
    _update_short_unrealized_nPnl,
    update_mae_and_mfe,
    update_position,
    update_unrealized_nPnl,
)


def _slot(val: int = 0) -> memoryview:
    """Creates an int64 memoryview scratch slot."""
    mv = memoryview(bytearray(8)).cast("q")
    mv[0] = val
    return mv


def _make_node_manager(
    leverage: int = 10, balance: float = 1_000.0
) -> MagicMock:
    mgr = MagicMock()
    mgr.cfgCoin = Coin(symbol="BTCUSDT", tick_size="0.01", lot_size="0.001")
    mgr.cfgAccount = Account(
        leverage=leverage,
        balance=balance,
        taker_commission=pct("0.05%"),
        maker_commission=pct("0.02%"),
        scale_prec=8,
    )
    return mgr


class ConcretePosition(Position):
    """Concrete subclass of Position for instantiation."""


class TestPositionClassInitAndBase:
    def test_position_fields_initialization(self):
        mgr = _make_node_manager(leverage=10, balance=1_000.0)
        pos = ConcretePosition(manager=mgr)

        assert pos.price_prec == 2
        assert pos.qty_prec == 3
        assert pos.price_mult == 100
        assert pos.qty_mult == 1_000
        assert pos.scale_prec == 8
        assert pos.scale_mult == 10**8
        assert pos.leverage == 10
        assert pos.startNbalance == 1_000 * 10**8

        # Memoryviews from Base
        assert pos.nBalance[0] == pos.startNbalance
        assert pos.availableNbalance[0] == pos.startNbalance
        assert pos.dynamicNbalance[0] == pos.startNbalance
        assert pos.lockedNbalance[0] == 0

        # Memoryviews from Position
        assert pos.longNqty[0] == 0
        assert pos.longEntryNprice[0] == 0
        assert pos.shortNqty[0] == 0
        assert pos.shortEntryNprice[0] == 0
        assert pos.unrealizedNpnl[0] == 0
        assert pos.longUnrealizedNpnl[0] == 0
        assert pos.shortUnrealizedNpnl[0] == 0
        assert pos.long_mae[0] == 0
        assert pos.long_mfe[0] == 0
        assert pos.short_mae[0] == 0
        assert pos.short_mfe[0] == 0

    def test_update_local_locked_nbalance(self):
        mgr = _make_node_manager(leverage=10)
        pos = ConcretePosition(manager=mgr)

        # 1. Long limit buy -> locks margin
        n_price = 50_000 * pos.price_mult
        n_qty = 1 * pos.qty_mult
        order_param = c.OF_LONG | c.OF_BUY | c.OF_LIMIT
        pos.update_local_lockedNbalance(n_price, n_qty, order_param)

        expected_margin = to_nMargin(
            n_price,
            n_qty,
            pos.leverage,
            pos.price_mult,
            pos.qty_mult,
            pos.scale_mult,
        )
        assert pos.lockedNbalance[0] == expected_margin

        # 2. Market order -> does not lock margin in update_local_lockedNbalance
        market_param = c.OF_LONG | c.OF_BUY | c.OF_MARKET
        pos.update_local_lockedNbalance(n_price, n_qty, market_param)
        assert pos.lockedNbalance[0] == expected_margin

        # 3. Short limit sell -> locks margin
        short_param = c.OF_SHORT | c.OF_SELL | c.OF_LIMIT
        pos.update_local_lockedNbalance(n_price, n_qty, short_param)
        assert pos.lockedNbalance[0] == expected_margin * 2

        # 4. Closing order (Long Sell) -> does not lock margin
        close_param = c.OF_LONG | c.OF_SELL | c.OF_LIMIT
        pos.update_local_lockedNbalance(n_price, n_qty, close_param)
        assert pos.lockedNbalance[0] == expected_margin * 2


class TestUpdatePositionLong:
    def test_open_long_first_entry_and_taker_margin(self):
        n_balance = _slot(1_000 * 10**8)
        locked_margin = _slot(0)
        long_qty = _slot(0)
        long_entry = _slot(0)
        long_mae = _slot(0)
        long_mfe = _slot(0)

        n_price = 50_000 * 100
        n_qty = 2 * 1_000
        commission = 5 * 10**8

        # Taker open long
        update_position(
            nPrice=n_price,
            nQty=n_qty,
            is_long=True,
            is_open=True,
            is_maker=False,
            nCommission=commission,
            price_mult=100,
            qty_mult=1_000,
            scale_mult=10**8,
            leverage=10,
            nBalance=n_balance,
            lockedNbalance=locked_margin,
            longNqty=long_qty,
            longEntryNprice=long_entry,
            shortNqty=_slot(0),
            shortEntryNprice=_slot(0),
            long_mae=long_mae,
            long_mfe=long_mfe,
            short_mae=_slot(0),
            short_mfe=_slot(0),
        )

        assert n_balance[0] == (1_000 * 10**8) - commission
        expected_margin = to_nMargin(n_price, n_qty, 10, 100, 1_000, 10**8)
        assert locked_margin[0] == expected_margin
        assert long_qty[0] == n_qty
        assert long_entry[0] == n_price

    def test_open_long_averaging_weighted_price(self):
        long_qty = _slot(2 * 1_000)
        long_entry = _slot(50_000 * 100)

        new_price = 60_000 * 100
        new_qty = 1 * 1_000

        _update_long_position(
            nPrice=new_price,
            nQty=new_qty,
            is_open=True,
            price_mult=100,
            qty_mult=1_000,
            scale_mult=10**8,
            leverage=10,
            nBalance=_slot(0),
            lockedNbalance=_slot(0),
            longNqty=long_qty,
            longEntryNprice=long_entry,
            long_mae=_slot(0),
            long_mfe=_slot(0),
        )

        # Expected: ((50000*2) + (60000*1)) / 3 = 160000 / 3 = 53333.333
        expected_price = (
            (50_000 * 100 * 2_000) + (60_000 * 100 * 1_000)
        ) // 3_000
        assert long_qty[0] == 3 * 1_000
        assert long_entry[0] == expected_price

    def test_close_long_partial_and_full(self):
        entry_price = 50_000 * 100
        total_qty = 2 * 1_000
        leverage = 10
        price_mult, qty_mult, scale_mult = 100, 1_000, 10**8

        long_qty = _slot(total_qty)
        long_entry = _slot(entry_price)
        long_mae = _slot(-500)
        long_mfe = _slot(1_000)
        initial_margin = to_nMargin(
            entry_price, total_qty, leverage, price_mult, qty_mult, scale_mult
        )
        locked_margin = _slot(initial_margin)
        n_balance = _slot(1_000 * scale_mult)

        # 1. Partial close 1 unit at 55_000 (profit)
        close_price_1 = 55_000 * price_mult
        close_qty_1 = 1 * qty_mult

        _update_long_position(
            nPrice=close_price_1,
            nQty=close_qty_1,
            is_open=False,
            price_mult=price_mult,
            qty_mult=qty_mult,
            scale_mult=scale_mult,
            leverage=leverage,
            nBalance=n_balance,
            lockedNbalance=locked_margin,
            longNqty=long_qty,
            longEntryNprice=long_entry,
            long_mae=long_mae,
            long_mfe=long_mfe,
        )

        margin_unlocked = to_nMargin(
            entry_price, close_qty_1, leverage, price_mult, qty_mult, scale_mult
        )
        assert locked_margin[0] == initial_margin - margin_unlocked
        assert long_qty[0] == 1 * qty_mult
        # Entry price and MAE/MFE remain while position is open
        assert long_entry[0] == entry_price
        assert long_mae[0] == -500
        assert long_mfe[0] == 1_000

        # 2. Full close remaining 1 unit at 52_000
        close_price_2 = 52_000 * price_mult
        close_qty_2 = 1 * qty_mult

        _update_long_position(
            nPrice=close_price_2,
            nQty=close_qty_2,
            is_open=False,
            price_mult=price_mult,
            qty_mult=qty_mult,
            scale_mult=scale_mult,
            leverage=leverage,
            nBalance=n_balance,
            lockedNbalance=locked_margin,
            longNqty=long_qty,
            longEntryNprice=long_entry,
            long_mae=long_mae,
            long_mfe=long_mfe,
        )

        assert long_qty[0] == 0
        assert locked_margin[0] == 0
        # When position reaches 0, price and stats are reset to 0
        assert long_entry[0] == 0
        assert long_mae[0] == 0
        assert long_mfe[0] == 0


class TestUpdatePositionShort:
    def test_open_short_first_entry_and_maker(self):
        n_balance = _slot(1_000 * 10**8)
        locked_margin = _slot(0)
        short_qty = _slot(0)
        short_entry = _slot(0)

        n_price = 40_000 * 100
        n_qty = 1 * 1_000
        commission = 2 * 10**8

        # Maker open short -> lockedNbalance is NOT directly modified here
        update_position(
            nPrice=n_price,
            nQty=n_qty,
            is_long=False,
            is_open=True,
            is_maker=True,
            nCommission=commission,
            price_mult=100,
            qty_mult=1_000,
            scale_mult=10**8,
            leverage=10,
            nBalance=n_balance,
            lockedNbalance=locked_margin,
            longNqty=_slot(0),
            longEntryNprice=_slot(0),
            shortNqty=short_qty,
            shortEntryNprice=short_entry,
            long_mae=_slot(0),
            long_mfe=_slot(0),
            short_mae=_slot(0),
            short_mfe=_slot(0),
        )

        assert n_balance[0] == (1_000 * 10**8) - commission
        assert locked_margin[0] == 0
        assert short_qty[0] == n_qty
        assert short_entry[0] == n_price

    def test_open_short_averaging_weighted_price(self):
        short_qty = _slot(1 * 1_000)
        short_entry = _slot(40_000 * 100)

        new_price = 45_000 * 100
        new_qty = 1 * 1_000

        _update_short_position(
            nPrice=new_price,
            nQty=new_qty,
            is_open=True,
            price_mult=100,
            qty_mult=1_000,
            scale_mult=10**8,
            leverage=10,
            nBalance=_slot(0),
            lockedNbalance=_slot(0),
            shortNqty=short_qty,
            shortEntryNprice=short_entry,
            short_mae=_slot(0),
            short_mfe=_slot(0),
        )

        expected_price = (
            (40_000 * 100 * 1_000) + (45_000 * 100 * 1_000)
        ) // 2_000
        assert short_qty[0] == 2 * 1_000
        assert short_entry[0] == expected_price

    def test_close_short_partial_and_full(self):
        entry_price = 40_000 * 100
        total_qty = 2 * 1_000
        leverage = 10
        price_mult, qty_mult, scale_mult = 100, 1_000, 10**8

        short_qty = _slot(total_qty)
        short_entry = _slot(entry_price)
        short_mae = _slot(-300)
        short_mfe = _slot(800)
        initial_margin = to_nMargin(
            entry_price, total_qty, leverage, price_mult, qty_mult, scale_mult
        )
        locked_margin = _slot(initial_margin)
        n_balance = _slot(1_000 * scale_mult)

        # 1. Partial close 1 unit at 38_000 (profit for short)
        close_price_1 = 38_000 * price_mult
        close_qty_1 = 1 * qty_mult

        _update_short_position(
            nPrice=close_price_1,
            nQty=close_qty_1,
            is_open=False,
            price_mult=price_mult,
            qty_mult=qty_mult,
            scale_mult=scale_mult,
            leverage=leverage,
            nBalance=n_balance,
            lockedNbalance=locked_margin,
            shortNqty=short_qty,
            shortEntryNprice=short_entry,
            short_mae=short_mae,
            short_mfe=short_mfe,
        )

        margin_unlocked = to_nMargin(
            entry_price, close_qty_1, leverage, price_mult, qty_mult, scale_mult
        )
        assert locked_margin[0] == initial_margin - margin_unlocked
        assert short_qty[0] == 1 * qty_mult
        assert short_entry[0] == entry_price
        assert short_mae[0] == -300
        assert short_mfe[0] == 800

        # 2. Full close remaining 1 unit at 42_000 (loss for short)
        close_price_2 = 42_000 * price_mult
        close_qty_2 = 1 * qty_mult

        _update_short_position(
            nPrice=close_price_2,
            nQty=close_qty_2,
            is_open=False,
            price_mult=price_mult,
            qty_mult=qty_mult,
            scale_mult=scale_mult,
            leverage=leverage,
            nBalance=n_balance,
            lockedNbalance=locked_margin,
            shortNqty=short_qty,
            shortEntryNprice=short_entry,
            short_mae=short_mae,
            short_mfe=short_mfe,
        )

        assert short_qty[0] == 0
        assert locked_margin[0] == 0
        assert short_entry[0] == 0
        assert short_mae[0] == 0
        assert short_mfe[0] == 0


class TestUnrealizedPnl:
    def test_update_unrealized_npnl_when_positions_open(self):
        price_mult, qty_mult, scale_mult = 100, 1_000, 10**8
        unrealized = _slot(0)
        long_unrealized = _slot(0)
        short_unrealized = _slot(0)

        long_qty = _slot(1 * qty_mult)
        long_entry = _slot(100 * price_mult)

        short_qty = _slot(1 * qty_mult)
        short_entry = _slot(110 * price_mult)

        cur_price = 105 * price_mult

        total_pnl = update_unrealized_nPnl(
            nPrice=cur_price,
            unrealizedNpnl=unrealized,
            longUnrealizedNpnl=long_unrealized,
            shortUnrealizedNpnl=short_unrealized,
            longNqty=long_qty,
            shortNqty=short_qty,
            longEntryNprice=long_entry,
            shortEntryNprice=short_entry,
            price_mult=price_mult,
            qty_mult=qty_mult,
            scale_mult=scale_mult,
        )

        expected_long = to_long_nPnl(
            cur_price,
            long_entry[0],
            long_qty[0],
            price_mult,
            qty_mult,
            scale_mult,
        )
        expected_short = to_short_nPnl(
            cur_price,
            short_entry[0],
            short_qty[0],
            price_mult,
            qty_mult,
            scale_mult,
        )

        assert long_unrealized[0] == expected_long
        assert short_unrealized[0] == expected_short
        assert unrealized[0] == expected_long + expected_short
        assert total_pnl == unrealized[0]

    def test_update_unrealized_npnl_when_positions_empty(self):
        unrealized = _slot(100)
        long_unrealized = _slot(50)
        short_unrealized = _slot(50)

        update_unrealized_nPnl(
            nPrice=100_00,
            unrealizedNpnl=unrealized,
            longUnrealizedNpnl=long_unrealized,
            shortUnrealizedNpnl=short_unrealized,
            longNqty=_slot(0),
            shortNqty=_slot(0),
            longEntryNprice=_slot(0),
            shortEntryNprice=_slot(0),
            price_mult=100,
            qty_mult=1_000,
            scale_mult=10**8,
        )

        assert long_unrealized[0] == 0
        assert short_unrealized[0] == 0
        assert unrealized[0] == 0

    def test_helpers_direct_zero_qty_branch(self):
        long_u = _slot(999)
        _update_long_unrealized_nPnl(
            nPrice=100,
            longUnrealizedNpnl=long_u,
            longNqty=_slot(0),
            longEntryNprice=_slot(0),
            price_mult=100,
            qty_mult=1_000,
            scale_mult=10**8,
        )
        assert long_u[0] == 0

        short_u = _slot(999)
        _update_short_unrealized_nPnl(
            nPrice=100,
            shortUnrealizedNpnl=short_u,
            shortNqty=_slot(0),
            shortEntryNprice=_slot(0),
            price_mult=100,
            qty_mult=1_000,
            scale_mult=10**8,
        )
        assert short_u[0] == 0


class TestMaeAndMfe:
    def test_update_long_mae_and_mfe(self):
        long_u = _slot(0)
        long_mae = _slot(0)
        long_mfe = _slot(0)

        # 1. Negative excursion (MAE)
        long_u[0] = -500
        _update_long_mae_and_mfe(long_u, long_mae, long_mfe)
        assert long_mae[0] == -500
        assert long_mfe[0] == 0

        # 2. Positive excursion (MFE)
        long_u[0] = 1_200
        _update_long_mae_and_mfe(long_u, long_mae, long_mfe)
        assert long_mae[0] == -500
        assert long_mfe[0] == 1_200

        # 3. Inside range -> no change
        long_u[0] = 500
        _update_long_mae_and_mfe(long_u, long_mae, long_mfe)
        assert long_mae[0] == -500
        assert long_mfe[0] == 1_200

    def test_update_short_mae_and_mfe(self):
        short_u = _slot(0)
        short_mae = _slot(0)
        short_mfe = _slot(0)

        # 1. Negative excursion
        short_u[0] = -800
        _update_short_mae_and_mfe(short_u, short_mae, short_mfe)
        assert short_mae[0] == -800
        assert short_mfe[0] == 0

        # 2. Positive excursion
        short_u[0] = 1_500
        _update_short_mae_and_mfe(short_u, short_mae, short_mfe)
        assert short_mae[0] == -800
        assert short_mfe[0] == 1_500

        # 3. Inside range -> no change
        short_u[0] = 0
        _update_short_mae_and_mfe(short_u, short_mae, short_mfe)
        assert short_mae[0] == -800
        assert short_mfe[0] == 1_500

    def test_update_mae_and_mfe_combined(self):
        long_u = _slot(-100)
        short_u = _slot(200)
        l_mae, l_mfe = _slot(0), _slot(0)
        s_mae, s_mfe = _slot(0), _slot(0)

        update_mae_and_mfe(long_u, short_u, l_mae, l_mfe, s_mae, s_mfe)
        assert l_mae[0] == -100
        assert l_mfe[0] == 0
        assert s_mae[0] == 0
        assert s_mfe[0] == 200
