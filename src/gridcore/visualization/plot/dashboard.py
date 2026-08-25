from matplotlib.axes import Axes

from ..analyze import Stats
from .utils import get_usd, not_data_for_plot


def plot_info_dashboard(ax: Axes, stats: Stats) -> None:
    if not stats.trades_close:
        return not_data_for_plot(ax)

    ax.axis("off")
    kpis: list[tuple[str, str, str]] = [
        (
            "Start Balance",
            f"${stats.start_balance:,.2f}",
            "#FFFFFF",
        ),
        (
            "End Balance",
            f"${(stats.end_balance):,.2f}",
            "#00E5FF",
        ),
        (
            "Net Profit",
            (
                f"{get_usd(stats.net_profit)}{abs(stats.net_profit):,.2f} "
                f"({stats.net_profit / stats.start_balance * 100:+.2f}%)"
            ),
            "#00E676" if stats.net_profit >= 0 else "#FF1744",
        ),
        (
            "Max Static DD",
            f"${stats.max_dd_val:,.2f} ({stats.max_dd_pct:.2f}%)",
            "#FF1744",
        ),
        (
            "Max Dynamic DD",
            f"${stats.max_dyn_dd_val:,.2f} ({stats.max_dyn_dd_pct:.2f}%)",
            "#FF9100",
        ),
        (
            "Profit / Recovery Factor",
            f"{stats.profit_factor:.2f} / {stats.recovery_factor:.2f}",
            "#FFFFFF",
        ),
        (
            "Sharpe / Sortino",
            f"{stats.sharpe_ratio:.2f} / {stats.sortino_ratio:.2f}",
            "#00E5FF" if stats.sharpe_ratio >= 0 else "#FF1744",
        ),
        (
            "Win Rate",
            f"{stats.win_rate:.1f}% ({stats.sum_tp_count}W / {stats.sum_sl_count}L)",
            "#00E676",
        ),
        (
            "EV (Expectancy)",
            f"{get_usd(stats.ev)}{abs(stats.ev):,.2f}",
            "#00E676" if stats.ev >= 0 else "#FF1744",
        ),
        (
            "Avg Win / MFE SL's",
            f"{get_usd(stats.avg_win)}{stats.avg_win:.2f} / {stats.avg_mfe_pct:+.2f}%",
            "#00E676",
        ),
        (
            "Avg Loss / MAE TP's",
            f"{get_usd(stats.avg_loss)}{abs(stats.avg_loss):.2f} / {stats.avg_mae_pct:+.2f}%",
            "#FF1744",
        ),
        (
            "Avg Hold Time",
            f"{stats.avg_hold_time_positions:.1f} min",
            "#FFFFFF",
        ),
        (
            "Paid Commission",
            f"${stats.sum_commission:,.2f}",
            "#FFD600",
        ),
    ]

    ax.text(
        0.05,
        1.0,
        f"SYSTEM KPI ({stats.symbol})",
        fontsize=12,
        fontweight="bold",
        color="#00E5FF",
        fontfamily="monospace",
    )
    ax.text(
        0.05,
        0.95,
        f"Period: {stats.start_date} to {stats.end_date}",
        fontsize=8,
        color="#757575",
        fontfamily="monospace",
    )

    y_pos: float = 0.90
    for label, val, color in kpis:
        y_pos -= 0.065
        ax.text(
            0.05,
            y_pos,
            f"{label:<22}",
            fontsize=9.5,
            color="#CFD8DC",
            fontfamily="monospace",
        )
        ax.text(
            0.58,
            y_pos,
            f"{val:>20}",
            fontsize=9.5,
            fontweight="bold",
            color=color,
            fontfamily="monospace",
        )
