"""Unit tests for `imprint.core.exchange.account.converter`."""

from pathlib import Path

import numpy as np
from numpy.typing import NDArray
from pytest import MonkeyPatch, fixture

from imprint.core import constant as c
from imprint.core.configs import Account, RiskManagement, pct
from imprint.core.exchange.account.converter import (
    Converter,
    to_long_nPnl,
    to_nMargin,
    to_short_nPnl,
)


def _slot() -> memoryview:
    return memoryview(bytearray(8)).cast("q")


@fixture
def con() -> Converter:
    account: Account = Account(
        leverage=10,
        balance=1_000.0,
        min_order_size=5.0,
        taker_commission=pct("0.05%"),
        maker_commission=pct("0.02%"),
        scale_prec=8,
        save_orders_history=True,
    )
    risk: RiskManagement = RiskManagement(
        entry_qty=pct("10%"),
        tp_dev=pct("2%"),
        sl_dev=pct("1%"),
        max_lock_balance=pct("50%"),
        max_loss_balance=pct("20%"),
    )
    con: Converter = Converter(
        cfgAccount=account, cfgStrategy=risk, price_prec=2, qty_prec=3
    )
    con.init_session(
        nBalance=_slot(),
        lockedNbalance=_slot(),
        availableNbalance=_slot(),
        longNqty=_slot(),
        longEntryNprice=_slot(),
        shortNqty=_slot(),
        shortEntryNprice=_slot(),
        unrealizedNpnl=_slot(),
        longUnrealizedNpnl=_slot(),
        shortUnrealizedNpnl=_slot(),
    )
    con._nBalance[0] = con.startNbalance
    con._availableNbalance[0] = con.startNbalance
    return con


class TestDerivedScalars:
    def test_scale_mult_and_start_balance(self) -> None:
        account: Account = Account(min_order_size=5.0, scale_prec=8)
        risk: RiskManagement = RiskManagement()
        con: Converter = Converter(
            cfgAccount=account, cfgStrategy=risk, price_prec=2, qty_prec=3
        )
        assert con.scale == 10**8
        assert con.startNbalance == round(1_000.0 * 10**8)
        assert con.timer == risk.pass_execute_signal_if_timer_ms_exepired

    def test_min_order_nsize_scaled(self) -> None:
        account: Account = Account(min_order_size=5.0, scale_prec=8)
        risk: RiskManagement = RiskManagement()
        con: Converter = Converter(
            cfgAccount=account, cfgStrategy=risk, price_prec=2, qty_prec=3
        )
        assert con.minOrderNsize == round(5.0 * 10**8)

    def test_percent_fields_are_unwrapped_to_int(self) -> None:
        risk: RiskManagement = RiskManagement(
            entry_qty=pct("10%"), tp_dev=pct("2%")
        )
        con: Converter = Converter(
            cfgAccount=Account(), cfgStrategy=risk, price_prec=2, qty_prec=3
        )
        assert con._entryQty == 1_000
        assert con._tpDev == 200


class TestBalanceAndPnlProperties:
    def test_balance_properties_getters(self, con: Converter) -> None:
        assert con.nBalance == con.startNbalance
        con._lockedNbalance[0] = 500
        assert con.lockedNbalance == 500
        con._availableNbalance[0] = 900
        assert con.availableNbalance == 900

    def test_unrealized_pnl_properties(self, con: Converter) -> None:
        con._unrealizedNpnl[0] = 1_234
        con._longUnrealizedNpnl[0] = 2_000
        con._shortUnrealizedNpnl[0] = -766
        assert con.unrealizedNpnl == 1_234
        assert con.longUnrealizedNpnl == 2_000
        assert con.shortUnrealizedNpnl == -766

    def test_loss_safe_limit_true_when_balance_untouched(
        self, con: Converter
    ) -> None:
        assert con.lossNbalanceSafeLimit is True

    def test_loss_safe_limit_false_once_breached(self, con: Converter) -> None:
        threshold: int = con.startNbalance - (
            con.startNbalance * con._max_loss_balance // 10_000
        )
        con._nBalance[0] = threshold
        assert con.lossNbalanceSafeLimit is False

    def test_locked_safe_limit_true_when_nothing_locked(
        self, con: Converter
    ) -> None:
        assert con.lockedNbalanceSafeLimit is True

    def test_locked_safe_limit_false_once_lock_cap_reached(
        self, con: Converter
    ) -> None:
        cap: int = con.nBalance * con._max_lock_balance // 10_000
        con._lockedNbalance[0] = cap
        assert con.lockedNbalanceSafeLimit is False


class TestEntrySizing:
    def test_nominal_entry_qty_is_available_balance_times_entry_pct(
        self, con: Converter
    ) -> None:
        expected = con.availableNbalance * con._entryQty // 10_000
        assert con.nominalEntryNqty == expected

    def test_nominal_entry_qty_with_leverage_above_min_order(
        self, con: Converter
    ) -> None:
        qty: int | None = con.nominalEntryNqtyWithLeverage
        assert qty is not None
        assert qty == con.leverage * con.nominalEntryNqty

    def test_nominal_entry_qty_with_leverage_none_below_min_order(self):
        account: Account = Account(
            leverage=1, balance=1.0, min_order_size=1_000_000.0, scale_prec=8
        )
        risk: RiskManagement = RiskManagement(entry_qty=pct("1%"))
        con: Converter = Converter(
            cfgAccount=account, cfgStrategy=risk, price_prec=2, qty_prec=3
        )
        con.init_session(
            _slot(),
            _slot(),
            _slot(),
            _slot(),
            _slot(),
            _slot(),
            _slot(),
            _slot(),
            _slot(),
            _slot(),
        )
        con._availableNbalance[0] = con.startNbalance
        assert con.nominalEntryNqtyWithLeverage is None

    def test_entry_qty_with_leverage_formula(self, con: Converter) -> None:
        nominal_nqty: int = 1_000 * con.scale
        n_price: int = 50_000 * con.priceMult
        qty: int = con.entryNqtyWithLeverage(n_price, nominal_nqty)
        nominal_qty_float: float = nominal_nqty / con.scale
        expected: int = round(
            (nominal_qty_float * con.priceMult * con.qtyMult) / n_price
        )
        assert qty == expected


class TestClientOrderId:
    def test_increments_from_one(self, con: Converter) -> None:
        assert con.newClientOrderId == 1
        assert con.newClientOrderId == 2
        assert con.newClientOrderId == 3


class TestTpSlParam:
    def test_long_take_profit_moves_price_up_and_sets_sell_limit(
        self, con: Converter
    ) -> None:
        n_price: int = 100_000
        tp_price, order_param = con.tp_sl_param(
            n_price, is_long=True, is_tp=True
        )
        expected_ticks: int = n_price * con._tpDev // 10_000
        assert tp_price == n_price + expected_ticks
        assert order_param & c.OF_LONG
        assert order_param & c.OF_SELL
        assert order_param & c.OF_LIMIT
        assert order_param & c.OF_OCO
        assert not (order_param & c.OF_SHORT)
        assert not (order_param & c.OF_BUY)

    def test_long_stop_loss_moves_price_down_and_sets_sell_trigger(
        self, con: Converter
    ) -> None:
        n_price: int = 100_000
        sl_price, order_param = con.tp_sl_param(
            n_price, is_long=True, is_tp=False
        )
        expected_ticks: int = n_price * con._slDev // 10_000
        assert sl_price == n_price - expected_ticks
        assert order_param & c.OF_LONG
        assert order_param & c.OF_SELL
        assert order_param & c.OF_MARKET_TRIGGER

    def test_short_take_profit_moves_price_down_and_sets_buy_limit(
        self, con: Converter
    ) -> None:
        n_price: int = 100_000
        tp_price, order_param = con.tp_sl_param(
            n_price, is_long=False, is_tp=True
        )
        expected_ticks: int = n_price * con._tpDev // 10_000
        assert tp_price == n_price - expected_ticks
        assert order_param & c.OF_SHORT
        assert order_param & c.OF_BUY
        assert order_param & c.OF_LIMIT

    def test_short_stop_loss_moves_price_up_and_sets_buy_trigger(
        self, con: Converter
    ) -> None:
        n_price: int = 100_000
        sl_price, order_param = con.tp_sl_param(
            n_price, is_long=False, is_tp=False
        )
        expected_ticks: int = n_price * con._slDev // 10_000
        assert sl_price == n_price + expected_ticks
        assert order_param & c.OF_SHORT
        assert order_param & c.OF_BUY
        assert order_param & c.OF_MARKET_TRIGGER


class TestIsAveraging:
    def test_new_long_buy_with_no_position_is_not_averaging(
        self, con: Converter
    ) -> None:
        order_param: int = c.OF_LONG | c.OF_BUY
        assert con.is_averaging(order_param) is False

    def test_long_buy_with_existing_long_qty_is_averaging(
        self, con: Converter
    ) -> None:
        con._longNqty[0] = 100
        order_param: int = c.OF_LONG | c.OF_BUY
        assert con.is_averaging(order_param) is True

    def test_long_buy_with_pending_orders_is_averaging(
        self, con: Converter
    ) -> None:
        con.have_pending_orders = True
        order_param: int = c.OF_LONG | c.OF_BUY
        assert con.is_averaging(order_param) is True

    def test_short_sell_with_no_position_is_not_averaging(
        self, con: Converter
    ) -> None:
        order_param: int = c.OF_SHORT | c.OF_SELL
        assert con.is_averaging(order_param) is False

    def test_short_sell_with_existing_short_qty_is_averaging(
        self, con: Converter
    ) -> None:
        con._shortNqty[0] = 100
        order_param: int = c.OF_SHORT | c.OF_SELL
        assert con.is_averaging(order_param) is True

    def test_short_sell_with_pending_orders_is_averaging(
        self, con: Converter
    ) -> None:
        con.have_pending_orders = True
        order_param: int = c.OF_SHORT | c.OF_SELL
        assert con.is_averaging(order_param) is True

    def test_closing_side_is_never_averaging(self, con: Converter) -> None:
        # LONG + SELL
        assert con.is_averaging(c.OF_LONG | c.OF_SELL) is False
        # SHORT + BUY
        assert con.is_averaging(c.OF_SHORT | c.OF_BUY) is False


class TestOrdersHistoryAndFinalAction:
    def test_update_appends_a_row_and_advances_write_index(
        self, con: Converter
    ) -> None:
        con.update_orders_history(
            timestamp=1_700_000_000_000,
            order_param=c.OF_LONG | c.OF_BUY,
            order_id=42,
            nPrice=100_000,
            nQty=10,
            nCommission=5,
            nMAE=-100,
            nMFE=200,
        )
        assert con.ohWid[0] == 1
        row: NDArray[np.int64] = con.orders_history[0]
        assert row[c.TP_timestamp] == 1_700_000_000_000
        assert row[c.TP_orderID] == 42
        assert row[c.TP_nPrice] == 100_000
        assert row[c.TP_nQty] == 10
        assert row[c.TP_commission] == 5
        assert row[c.TP_nMAE] == -100
        assert row[c.TP_nMFE] == 200

    def test_buffer_grows_once_capacity_is_exceeded(
        self, con: Converter
    ) -> None:
        con.oh_rows = 2
        con.orders_history = con.orders_history[:2].copy()
        for i in range(3):
            con.update_orders_history(
                timestamp=i,
                order_param=0,
                order_id=i,
                nPrice=0,
                nQty=0,
                nCommission=0,
            )
        assert con.orders_history.shape[0] >= 4
        assert con.ohWid[0] == 3

    def test_final_action_saves_when_flag_is_true(
        self, con: Converter, monkeypatch: MonkeyPatch, tmp_path: Path
    ) -> None:
        save_dest: Path = tmp_path / "order_history.npy"
        monkeypatch.setattr(c, "ORDERS_HISTORY_DUMP_PATH", str(save_dest))
        con.cfgAC.save_orders_history = True
        con.update_orders_history(
            timestamp=123,
            order_param=1,
            order_id=2,
            nPrice=3,
            nQty=4,
            nCommission=5,
        )
        con.final_action()
        assert save_dest.exists()
        loaded = np.load(str(save_dest))
        assert loaded.shape[0] == 1
        assert loaded[0, c.TP_timestamp] == 123

    def test_final_action_does_not_save_when_flag_is_false(
        self, con: Converter, monkeypatch: MonkeyPatch, tmp_path: Path
    ) -> None:
        save_dest: Path = tmp_path / "order_history.npy"
        monkeypatch.setattr(c, "ORDERS_HISTORY_DUMP_PATH", str(save_dest))
        con.cfgAC.save_orders_history = False
        con.final_action()
        assert not save_dest.exists()


class TestNjitHelpers:
    def test_to_nmargin_matches_manual_formula(self) -> None:
        n_price, n_qty, leverage = 5_000_000, 10_000, 10
        price_mult, qty_mult, scale_mult = 100, 1_000, 10**8
        result = to_nMargin(
            n_price, n_qty, leverage, price_mult, qty_mult, scale_mult
        )
        margin = ((n_qty / qty_mult) * (n_price / price_mult)) / leverage
        assert result == round(margin * scale_mult)

    def test_to_long_npnl_is_positive_when_price_rises(self) -> None:
        result = to_long_nPnl(
            closeNprice=110_00,
            entryNprice=100_00,
            nQty=1_000,
            price_mult=100,
            qty_mult=1_000,
            scale_mult=10**8,
        )
        assert result > 0

    def test_to_long_npnl_is_negative_when_price_falls(self) -> None:
        result = to_long_nPnl(
            closeNprice=90_00,
            entryNprice=100_00,
            nQty=1_000,
            price_mult=100,
            qty_mult=1_000,
            scale_mult=10**8,
        )
        assert result < 0

    def test_to_short_npnl_is_positive_when_price_falls(self) -> None:
        result = to_short_nPnl(
            closeNprice=90_00,
            entryNprice=100_00,
            nQty=1_000,
            price_mult=100,
            qty_mult=1_000,
            scale_mult=10**8,
        )
        assert result > 0

    def test_to_short_npnl_is_negative_when_price_rises(self) -> None:
        result = to_short_nPnl(
            closeNprice=110_00,
            entryNprice=100_00,
            nQty=1_000,
            price_mult=100,
            qty_mult=1_000,
            scale_mult=10**8,
        )
        assert result < 0

    def test_long_and_short_pnl_are_mirror_images(self) -> None:
        kwargs: dict[str, int] = {
            "closeNprice": 110_00,
            "entryNprice": 100_00,
            "nQty": 1_000,
            "price_mult": 100,
            "qty_mult": 1_000,
            "scale_mult": 10**8,
        }
        assert to_long_nPnl(**kwargs) == -to_short_nPnl(**kwargs)
