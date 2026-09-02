import matplotlib.dates as mdates
import matplotlib.gridspec as gridspec
import matplotlib.pyplot as plt
from matplotlib.axes import Axes
from matplotlib.figure import Figure

from ..analyze import Stats
from ..plot import (
    plot_chart_with_markers,
    plot_curve_balance,
    plot_info_dashboard,
    plot_trade_distribution,
)


def run(stats: Stats) -> None:
    plt.style.use("dark_background")
    fig: Figure = plt.figure(figsize=(16, 9), facecolor="#121212")  # pyright: ignore[reportUnknownMemberType]
    gs = gridspec.GridSpec(
        2, 2, width_ratios=[3.0, 1.3], height_ratios=[1.0, 1.2], figure=fig
    )

    ax_equity: Axes = fig.add_subplot(gs[0, 0], facecolor="#181818")
    ax_chart: Axes = fig.add_subplot(gs[1, 0], facecolor="#181818", sharex=ax_equity)
    ax_dashboard: Axes = fig.add_subplot(gs[0, 1], facecolor="#121212")
    ax_dist: Axes = fig.add_subplot(gs[1, 1], facecolor="#181818")

    plot_curve_balance(ax_equity, stats)
    plot_chart_with_markers(ax_chart, stats)
    plot_info_dashboard(ax_dashboard, stats)
    plot_trade_distribution(ax_dist, stats)

    ax_chart.xaxis.set_major_formatter(mdates.DateFormatter("%m-%d %H:%M"))
    ax_chart.xaxis.set_major_locator(mdates.AutoDateLocator())
    plt.setp(ax_equity.get_xticklabels(), visible=False)  # pyright: ignore[reportUnknownMemberType]
    fig.subplots_adjust(
        left=0.05, bottom=0.06, right=0.96, top=0.94, wspace=0.15, hspace=0.16
    )
    plt.show()  # pyright: ignore[reportUnknownMemberType]
