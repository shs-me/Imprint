from datetime import datetime

from matplotlib.axes import Axes
from numpy import float64

from imprint.visualization.analyze import Stats
from imprint.visualization.plot.utils import (
    not_data_for_plot,
    run_base_action,
    set_ax_pct,
    set_base_legend,
    set_base_title,
    set_base_ylabel,
)


def plot_chart_with_markers(ax: Axes, stats: Stats) -> None:
    if not stats.ohlc["time"][0]:
        return not_data_for_plot(ax)

    # Base Price Line
    base_price: float64 = stats.ohlc["close"][0]
    ax.axhline(  # pyright: ignore[reportUnknownMemberType])
        base_price,
        color="#757575",
        linestyle="--",
        linewidth=0.9,
        alpha=0.7,
        label=f"Start Price (${base_price:,.2f})",
        zorder=2,
    )

    # Price Line
    ax.plot(  # pyright: ignore[reportUnknownMemberType])
        stats.ohlc["time"],
        stats.ohlc["close"],
        color="#546E7A",
        alpha=0.6,
        linewidth=1.0,
        zorder=3,
    )

    ax.fill_between(  # pyright: ignore[reportUnknownMemberType])
        stats.ohlc["time"],
        base_price,
        stats.ohlc["close"],
        where=(stats.ohlc["close"] >= base_price),
        color="#00E676",
        alpha=0.12,
        interpolate=True,
        zorder=2,
    )
    ax.fill_between(  # pyright: ignore[reportUnknownMemberType])
        stats.ohlc["time"],
        base_price,
        stats.ohlc["close"],
        where=(stats.ohlc["close"] < base_price),
        color="#FF1744",
        alpha=0.12,
        interpolate=True,
        zorder=2,
    )

    # Markers Long / Short / Close
    buy_x: list[datetime] = [
        to["time"] for to in stats.trades_open if to["is_long"]
    ]
    buy_y: list[float] = [
        to["price"] for to in stats.trades_open if to["is_long"]
    ]
    ax.scatter(  # pyright: ignore[reportUnknownMemberType])
        buy_x,  # pyright: ignore[reportArgumentType])
        buy_y,
        marker="^",
        color="#00E676",
        s=50,
        edgecolors="#121212",
        linewidths=0.5,
        label="Long Entry",
        zorder=5,
    )

    sell_x: list[datetime] = [
        to["time"] for to in stats.trades_open if not to["is_long"]
    ]
    sell_y: list[float] = [
        to["price"] for to in stats.trades_open if not to["is_long"]
    ]
    ax.scatter(  # pyright: ignore[reportUnknownMemberType])
        sell_x,  # pyright: ignore[reportArgumentType])
        sell_y,
        marker="v",
        color="#FF1744",
        s=50,
        edgecolors="#121212",
        linewidths=0.5,
        label="Short Entry",
        zorder=5,
    )

    close_long_x: list[datetime] = [
        tc["time"] for tc in stats.trades_close if tc["is_long"]
    ]
    close_long_y: list[float] = [
        tc["price"] for tc in stats.trades_close if tc["is_long"]
    ]
    ax.scatter(  # pyright: ignore[reportUnknownMemberType])
        close_long_x,  # pyright: ignore[reportArgumentType])
        close_long_y,
        marker="x",
        color="#00E676",
        s=35,
        linewidths=0.8,
        label="Close Long",
        zorder=4,
    )

    close_short_x: list[datetime] = [
        tc["time"] for tc in stats.trades_close if not tc["is_long"]
    ]
    close_short_y: list[float] = [
        tc["price"] for tc in stats.trades_close if not tc["is_long"]
    ]
    ax.scatter(  # pyright: ignore[reportUnknownMemberType])
        close_short_x,  # pyright: ignore[reportArgumentType])
        close_short_y,
        marker="x",
        color="#FF1744",
        s=35,
        linewidths=0.8,
        label="Close Short",
        zorder=4,
    )

    run_base_action(ax)
    set_ax_pct(ax, base_price)
    set_base_title(ax, "PRICE & TRADE EXECUTIONS")
    set_base_ylabel(ax, "Price (Left $ | Right %)")
    set_base_legend(ax, False)
