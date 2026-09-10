from plotly.graph_objects import (  # pyright: ignore[reportMissingTypeStubs]
    Figure,
    Table,
)

from imprint._vis.analyze import Stats
from imprint._vis.plot.utils import (
    apply_dark_theme,
    empty_figure,
    get_usd,
)


def plot_info_dashboard(stats: Stats) -> Figure:
    if not stats.trades_close:
        return empty_figure()

    if stats.sqn >= 3.0:
        sqn_desc = "Excellent"
        sqn_col = "#00E676"
    elif stats.sqn >= 2.0:
        sqn_desc = "Good"
        sqn_col = "#00E5FF"
    elif stats.sqn >= 1.6:
        sqn_desc = "Average"
        sqn_col = "#FFD600"
    else:
        sqn_desc = "Poor"
        sqn_col = "#FF1744"

    left_metrics = [
        ("--- CAPITAL & RETURNS ---", "", "#00E5FF"),
        ("Start Balance", f"${stats.start_balance:,.2f}", "#FFFFFF"),
        ("End Balance", f"${stats.end_balance:,.2f}", "#00E5FF"),
        (
            "Net Profit",
            f"{get_usd(stats.net_profit)}{abs(stats.net_profit):,.2f} ({stats.net_profit / stats.start_balance * 100:+.2f}%)",
            "#00E676" if stats.net_profit >= 0 else "#FF1744",
        ),
        ("Turnover (Volume)", f"${stats.turnover:,.2f}", "#FFFFFF"),
        ("Paid Commission", f"${stats.sum_commission:,.2f}", "#FFD600"),
        ("--- RISK & RATIOS ---", "", "#00E5FF"),
        (
            "Max Static Drawdown",
            f"${stats.max_dd_val:,.2f} ({stats.max_dd_pct:.2f}%)",
            "#FF1744",
        ),
        (
            "Max Dynamic Drawdown",
            f"${stats.max_dyn_dd_val:,.2f} ({stats.max_dyn_dd_pct:.2f}%)",
            "#FF9100",
        ),
        (
            "Profit Factor / Recovery",
            f"{stats.profit_factor:.2f} / {stats.recovery_factor:.2f}",
            "#FFFFFF",
        ),
        (
            "Sharpe / Sortino",
            f"{stats.sharpe_ratio:.2f} / {stats.sortino_ratio:.2f}",
            "#00E5FF" if stats.sharpe_ratio >= 0 else "#FF1744",
        ),
        (
            "Calmar Ratio",
            f"{stats.calmar_ratio:.2f}",
            "#00E676" if stats.calmar_ratio >= 1.0 else "#FF1744",
        ),
    ]

    right_metrics = [
        ("--- TRADE DYNAMICS ---", "", "#00E5FF"),
        (
            "Win Rate",
            f"{stats.win_rate:.1f}% ({stats.sum_tp_count}W / {stats.sum_sl_count}L)",
            "#00E676",
        ),
        (
            "Long WR / PnL",
            f"{stats.long_wr:.1f}% / {get_usd(stats.long_pnl)}{abs(stats.long_pnl):,.2f}",
            "#00E676" if stats.long_pnl >= 0 else "#FF1744",
        ),
        (
            "Short WR / PnL",
            f"{stats.short_wr:.1f}% / {get_usd(stats.short_pnl)}{abs(stats.short_pnl):,.2f}",
            "#00E676" if stats.short_pnl >= 0 else "#FF1744",
        ),
        (
            "Max Win / Loss Streak",
            f"{stats.max_win_streak}W / {stats.max_loss_streak}L",
            "#FFFFFF",
        ),
        ("System Quality (SQN)", f"{stats.sqn:.2f} ({sqn_desc})", sqn_col),
        (
            "Kelly Criterion",
            f"{stats.kelly_pct:+.1f}%",
            "#00E676" if stats.kelly_pct > 0 else "#FF1744",
        ),
        ("--- EDGE & EXCURSIONS ---", "", "#00E5FF"),
        (
            "EV (Expectancy)",
            f"{get_usd(stats.ev)}{abs(stats.ev):,.2f}",
            "#00E676" if stats.ev >= 0 else "#FF1744",
        ),
        (
            "Payoff Ratio (Win/Loss)",
            f"{stats.payoff_ratio:.2f}",
            "#00E676" if stats.payoff_ratio >= 1.0 else "#FF9100",
        ),
        (
            "Avg Win / MFE (on SLs)",
            f"{get_usd(stats.avg_win)}{stats.avg_win:.2f} / {stats.avg_mfe_pct:+.2f}%",
            "#00E676",
        ),
        (
            "Avg Loss / MAE (on TPs)",
            f"{get_usd(stats.avg_loss)}{abs(stats.avg_loss):.2f} / {stats.avg_mae_pct:+.2f}%",
            "#FF1744",
        ),
        (
            "Avg Position Hold Time",
            f"{stats.avg_hold_time_positions:.1f} min",
            "#FFFFFF",
        ),
    ]

    l_labels = [item[0] for item in left_metrics]
    l_values = [item[1] for item in left_metrics]
    l_colors = [item[2] for item in left_metrics]

    r_labels = [item[0] for item in right_metrics]
    r_values = [item[1] for item in right_metrics]
    r_colors = [item[2] for item in right_metrics]

    # Стилизация фона строк-разделителей
    row_bg_l = [
        "#1A2327" if "---" in label else "#121212" for label in l_labels
    ]
    row_bg_r = [
        "#1A2327" if "---" in label else "#121212" for label in r_labels
    ]

    fig = Figure(
        data=[
            Table(
                columnorder=[1, 2, 3, 4],
                columnwidth=[260, 200, 260, 200],
                header={
                    "values": [
                        "<b>PORTFOLIO & RISK METRIC</b>",
                        "<b>VALUE</b>",
                        "<b>EXECUTION & EDGE METRIC</b>",
                        "<b>VALUE</b>",
                    ],
                    "fill_color": "#1E1E1E",
                    "align": ["left", "right", "left", "right"],
                    "font": {
                        "color": "#00E5FF",
                        "size": 12,
                        "family": "'Courier New', Consolas, monospace",
                    },
                    "height": 32,
                    "line_color": "#263238",
                },
                cells={
                    "values": [l_labels, l_values, r_labels, r_values],
                    "fill_color": [row_bg_l, row_bg_l, row_bg_r, row_bg_r],
                    "align": ["left", "right", "left", "right"],
                    "font": {
                        "color": [
                            [
                                "#00E5FF" if "---" in x else "#CFD8DC"
                                for x in l_labels
                            ],
                            l_colors,
                            [
                                "#00E5FF" if "---" in x else "#CFD8DC"
                                for x in r_labels
                            ],
                            r_colors,
                        ],
                        "size": 11,
                        "family": "'Courier New', Consolas, monospace",
                    },
                    "height": 27,
                    "line_color": "#1E1E1E",
                },
            )
        ]
    )

    fig.update_layout(  # pyright: ignore[reportUnknownMemberType]
        autosize=True,
        margin={"l": 30, "r": 30, "t": 35, "b": 25},
    )

    return apply_dark_theme(
        fig, f"SYSTEM PERFORMANCE & QUANTITATIVE KPI ({stats.symbol})"
    )
