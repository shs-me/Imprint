import os
import webbrowser
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from importlib import resources

import numpy as np
from loguru import logger
from numpy import int64
from numpy.typing import NDArray
from plotly.graph_objects import (  # pyright: ignore[reportMissingTypeStubs]
    Figure,
)

import imprint._vis as ivis
from imprint._core import constant as c
from imprint._core.settings import Timeframe
from imprint._vis.analyze import Stats
from imprint._vis.plot import (
    plot_equity_and_chart,
    plot_info_dashboard,
    plot_trade_distribution,
)
from imprint._vis.settings import OHLC


@dataclass(slots=True)
class Render:
    footprint_headers_path: str
    symbol: str
    start_date_str: str
    end_date_str: str
    equity_history_path: str
    orders_history_path: str
    start_balance: float
    price_mult: int
    qty_mult: int
    scale_mult: int
    leverage: int
    timeframe: Timeframe

    auto_open: bool

    output_path: str = field(default=c.REPORT_DATA_PATH, init=False)
    template_name: str = field(default="template.html", init=False)
    path_to_template: str = field(default=ivis.__name__, init=False)

    equity_history: NDArray[int64] = field(init=False)
    orders_history: NDArray[int64] = field(init=False)
    start_date: datetime = field(init=False)
    end_date: datetime = field(init=False)
    headers_path: str | None = field(init=False)
    headers: NDArray[int64] = field(init=False)
    ohlc: OHLC = field(init=False)
    stats: Stats = field(init=False)

    def __post_init__(self) -> None:
        self.equity_history = np.load(file=self.equity_history_path)
        self.orders_history = np.load(file=self.orders_history_path)

        self.start_date = datetime.fromisoformat(self.start_date_str).replace(
            tzinfo=UTC
        )
        self.end_date = datetime.fromisoformat(self.end_date_str).replace(
            tzinfo=UTC
        )

        self.headers_path = self.get_headers_path()
        if self.headers_path is None:
            return logger.warning(
                f"Not found headers with setup: {self.timeframe.name} | "
                + f"{self.start_date.date()} | {self.end_date.date()}"
            )

        self.headers = np.load(self.headers_path)
        self.headers = self.get_need_headers_range()
        self.ohlc = self.get_ohlc()

        self.stats = Stats(
            symbol=self.symbol,
            start_date=self.start_date_str,
            end_date=self.end_date_str,
            start_balance=self.start_balance,
            leverage=self.leverage,
            timeframe=self.timeframe,
            price_mult=self.price_mult,
            qty_mult=self.qty_mult,
            scale_mult=self.scale_mult,
            equity=self.equity_history,
            orders=self.orders_history,
            ohlc=self.ohlc,
        )
        self.run()

    def get_headers_path(self) -> str | None:
        base_headers_path: str = f"{self.footprint_headers_path}/{self.symbol}"

        paths: list[str] = [
            p.split(".npy")[0]
            for p in os.listdir(base_headers_path)
            if p.endswith(".npy")
        ]
        if paths:
            for p in paths:
                file_timeframe, file_start_time, file_end_time = p.split("_")
                if file_timeframe == self.timeframe.name:
                    file_start_date: date = date.fromisoformat(file_start_time)
                    file_end_date: date = date.fromisoformat(file_end_time)
                    if (
                        file_start_date
                        <= self.start_date.date()
                        <= self.end_date.date()
                        <= file_end_date
                    ):
                        return f"{base_headers_path}/{p}.npy"

    def get_need_headers_range(self) -> NDArray[int64]:
        start_ts: int = round(self.start_date.timestamp() * 1000)
        end_ts: int = round(
            (self.end_date + timedelta(days=1)).timestamp() * 1000
        )

        times: NDArray[int64] = self.headers[:, c.BH_Time]

        idx_start: np.intp = np.searchsorted(times, start_ts, side="left")
        idx_end: np.intp = np.searchsorted(times, end_ts, side="right")

        return self.headers[idx_start:idx_end, :]

    def get_ohlc(self) -> OHLC:
        ohlc: OHLC = {
            "open": self.headers[:, c.BH_Open] / self.price_mult,
            "high": self.headers[:, c.BH_High] / self.price_mult,
            "low": self.headers[:, c.BH_Low] / self.price_mult,
            "close": self.headers[:, c.BH_Close] / self.price_mult,
            "time": self.headers[:, c.BH_Time].astype("datetime64[ms]"),
        }
        return ohlc

    def to_html_div(self, fig: Figure) -> str:
        return fig.to_html(  # pyright: ignore[reportUnknownMemberType]
            full_html=False,
            include_plotlyjs=False,
            config={"responsive": True, "displayModeBar": True},
        )

    def run(self) -> None:
        os.makedirs(os.path.dirname(self.output_path), exist_ok=True)

        div_dashboard: str = self.to_html_div(plot_info_dashboard(self.stats))
        div_dist: str = self.to_html_div(plot_trade_distribution(self.stats))
        div_equity_and_price: str = self.to_html_div(
            plot_equity_and_chart(self.stats)
        )

        with resources.open_text(
            self.path_to_template, self.template_name
        ) as f:
            html: str = f.read().format(
                symbol=self.symbol,
                start_date=self.start_date_str,
                end_date=self.end_date_str,
                div_dashboard=div_dashboard,
                div_dist=div_dist,
                div_equity_and_price=div_equity_and_price,
            )

        with open(self.output_path, "w", encoding="utf-8") as f:
            f.write(html)

        abs_path = os.path.abspath(self.output_path)
        if self.auto_open:
            webbrowser.open(f"file://{abs_path}")
