import matplotlib.ticker as mticker
from matplotlib.axes import Axes


def get_usd(val: float | int) -> str:
    return "+$" if val >= 0 else "-$"


def not_data_for_plot(ax: Axes, text: str = "No Trades To Display") -> None:
    ax.text(
        0.5,
        0.5,
        text,
        ha="center",
        va="center",
        color="#757575",
        fontfamily="monospace",
    )
    ax.axis("off")


def run_base_action(ax: Axes) -> None:
    ax.tick_params(colors="#757575", labelsize=8)
    ax.grid(True, color="#212121", linestyle="--", alpha=0.5)


def set_ax_pct(ax: Axes, base_tick) -> None:
    ax_pct = ax.twinx()
    ymin, ymax = ax.get_ylim()
    pct_min = ((ymin - base_tick) / base_tick) * 100.0
    pct_max = ((ymax - base_tick) / base_tick) * 100.0
    ax_pct.set_ylim(pct_min, pct_max)
    ax_pct.tick_params(axis="y", labelcolor="#757575", labelsize=8)
    ax_pct.yaxis.set_major_formatter(mticker.FuncFormatter(lambda y, _: f"{y:+.1f}%"))


def set_base_title(ax, text: str) -> None:
    ax.set_title(
        text, fontsize=11, fontweight="bold", color="#B0BEC5", fontfamily="monospace"
    )


def set_base_xlabel(ax: Axes, text: str) -> None:
    ax.set_xlabel(text, color="#b0BEC5", fontsize=9, fontfamily="monospace")


def set_base_ylabel(ax: Axes, text: str) -> None:
    ax.set_ylabel(text, color="#b0BEC5", fontsize=9, fontfamily="monospace")


def set_base_legend(ax: Axes, right: bool = True) -> None:
    ax.legend(
        fontsize=7,
        loc="upper right" if right else "upper left",
        facecolor="#121212",
        edgecolor="#212121",
    )
