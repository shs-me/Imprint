import base64
import io
import os
import webbrowser
from datetime import timezone
from importlib import resources
from types import FunctionType

import matplotlib.dates as mdates
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


def _render_to_base64(
    plot_fn: FunctionType,
    stats: Stats,
    figsize: tuple[float, float] = (14, 7),
    is_dashboard: bool = False,
) -> str:
    plt.style.use("dark_background")

    fig: Figure = plt.figure(  # pyright: ignore[reportUnknownMemberType]
        figsize=figsize,
        facecolor="#121212",
        dpi=120,
    )
    ax: Axes = fig.add_subplot(
        1, 1, 1, facecolor="#121212" if is_dashboard else "#181818"
    )

    plot_fn(ax, stats)

    if not is_dashboard and plot_fn == plot_chart_with_markers:
        ax.xaxis.set_major_formatter(
            mdates.DateFormatter("%m-%d %H:%M", tz=timezone.utc)
        )
        ax.xaxis.set_major_locator(mdates.AutoDateLocator(tz=timezone.utc))

    fig.tight_layout()

    buf: io.BytesIO = io.BytesIO()
    fig.savefig(  # pyright: ignore[reportUnknownMemberType]
        buf,
        format="png",
        facecolor=fig.get_facecolor(),
        edgecolor="none",
    )
    plt.close(fig)
    buf.seek(0)
    return base64.b64encode(buf.getvalue()).decode("utf-8")


def run(
    stats: Stats,
    output_path: str = "dump/report.html",
    template_name: str = "template.html",
    path_to_template: str = "gridcore.visualization.render",
    auto_open: bool = True,
) -> str:
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    img_equity: str = _render_to_base64(plot_curve_balance, stats, figsize=(15, 7.5))
    img_chart: str = _render_to_base64(
        plot_chart_with_markers, stats, figsize=(15, 7.5)
    )
    img_dashboard: str = _render_to_base64(
        plot_info_dashboard, stats, figsize=(10, 7.5), is_dashboard=True
    )
    img_dist: str = _render_to_base64(plot_trade_distribution, stats, figsize=(12, 7.5))

    with resources.open_text(path_to_template, template_name) as f:
        html: str = f.read().format(
            symbol=stats.symbol,
            start_date=stats.start_date,
            end_date=stats.end_date,
            img_equity=img_equity,
            img_chart=img_chart,
            img_dashboard=img_dashboard,
            img_dist=img_dist,
        )

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)

    abs_path = os.path.abspath(output_path)
    if auto_open:
        webbrowser.open(f"file://{abs_path}")

    return abs_path
