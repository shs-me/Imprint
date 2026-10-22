from dataclasses import dataclass, field

from plotly.graph_objects import (  # pyright: ignore[reportMissingTypeStubs]
    Figure,
)

from imprint._vis.analyze import Stats
from imprint._vis.plot.utils import (
    apply_dark_theme,
    empty_figure,
    get_usd,
)

# Colors
C_ACCENT = "#00E5FF"
C_GOOD = "#00E676"
C_BAD = "#FF1744"
C_WARN = "#FFD600"
C_ORANGE = "#FF9100"
C_TEXT = "#CFD8DC"
C_WHITE = "#FFFFFF"
C_ROW_A = "#121212"
C_ROW_B = "#161616"
C_HEADER_BG = "#1A2327"
C_BORDER = "#263238"

FONT = "'Courier New', Consolas, monospace"

# Pixel geometry
ROW_H = 30
SECTION_H = 38
SECTION_GAP = 14
TOP_PAD = 60
BOTTOM_PAD = 20
COL_GAP = 0.04  # in column-width units


@dataclass(frozen=True, slots=True)
class Metric:
    label: str
    value: str
    color: str = C_WHITE


@dataclass(frozen=True, slots=True)
class Section:
    title: str
    metrics: list[Metric] = field(default_factory=list[Metric])

    @property
    def height(self) -> int:
        return SECTION_H + ROW_H * len(self.metrics) + SECTION_GAP


def _pnl_color(val: float) -> str:
    return C_GOOD if val >= 0 else C_BAD


def _signed(val: float) -> str:
    return f"{get_usd(val)}{abs(val):,.2f}"


def build_sections(stats: Stats) -> list[Section]:
    if stats.sqn >= 3.0:
        sqn_desc, sqn_col = "Excellent", C_GOOD
    elif stats.sqn >= 2.0:
        sqn_desc, sqn_col = "Good", C_ACCENT
    elif stats.sqn >= 1.6:
        sqn_desc, sqn_col = "Average", C_WARN
    else:
        sqn_desc, sqn_col = "Poor", C_BAD

    net_pct: float = (
        stats.net_profit / stats.start_balance * 100
        if stats.start_balance
        else 0.0
    )

    return [
        Section(
            "CAPITAL & RETURNS",
            [
                Metric("Start Balance", f"${stats.start_balance:,.2f}"),
                Metric("End Balance", f"${stats.end_balance:,.2f}", C_ACCENT),
                Metric(
                    "Net Profit",
                    f"{_signed(stats.net_profit)} ({net_pct:+.2f}%)",
                    _pnl_color(stats.net_profit),
                ),
                Metric("Turnover (Volume)", f"${stats.turnover:,.2f}"),
                Metric(
                    "Paid Commission", f"${stats.sum_commission:,.2f}", C_WARN
                ),
            ],
        ),
        Section(
            "RISK & RATIOS",
            [
                Metric(
                    "Max Static Drawdown",
                    f"${stats.max_dd_val:,.2f} ({stats.max_dd_pct:.2f}%)",
                    C_BAD,
                ),
                Metric(
                    "Max Dynamic Drawdown",
                    f"${stats.max_dyn_dd_val:,.2f} ({stats.max_dyn_dd_pct:.2f}%)",
                    C_ORANGE,
                ),
                Metric(
                    "Profit Factor / Recovery",
                    f"{stats.profit_factor:.2f} / {stats.recovery_factor:.2f}",
                ),
                Metric(
                    "Sharpe / Sortino",
                    f"{stats.sharpe_ratio:.2f} / {stats.sortino_ratio:.2f}",
                    C_ACCENT if stats.sharpe_ratio >= 0 else C_BAD,
                ),
                Metric(
                    "Calmar Ratio",
                    f"{stats.calmar_ratio:.2f}",
                    C_GOOD if stats.calmar_ratio >= 1.0 else C_BAD,
                ),
            ],
        ),
        Section(
            "TRADE DYNAMICS",
            [
                Metric(
                    "Win Rate",
                    f"{stats.win_rate:.1f}% ({stats.sum_tp_count}W / {stats.sum_sl_count}L)",
                    C_GOOD,
                ),
                Metric(
                    "Long WR / PnL",
                    f"{stats.long_wr:.1f}% / {_signed(stats.long_pnl)}",
                    _pnl_color(stats.long_pnl),
                ),
                Metric(
                    "Short WR / PnL",
                    f"{stats.short_wr:.1f}% / {_signed(stats.short_pnl)}",
                    _pnl_color(stats.short_pnl),
                ),
                Metric(
                    "Max Win / Loss Streak",
                    f"{stats.max_win_streak}W / {stats.max_loss_streak}L",
                ),
                Metric(
                    "System Quality (SQN)",
                    f"{stats.sqn:.2f} ({sqn_desc})",
                    sqn_col,
                ),
                Metric(
                    "Kelly Criterion",
                    f"{stats.kelly_pct:+.1f}%",
                    C_GOOD if stats.kelly_pct > 0 else C_BAD,
                ),
            ],
        ),
        Section(
            "EDGE & EXCURSIONS",
            [
                Metric(
                    "EV (Expectancy)", _signed(stats.ev), _pnl_color(stats.ev)
                ),
                Metric(
                    "Payoff Ratio (Win/Loss)",
                    f"{stats.payoff_ratio:.2f}",
                    C_GOOD if stats.payoff_ratio >= 1.0 else C_ORANGE,
                ),
                Metric(
                    "Avg Win / MFE (on SLs)",
                    f"{get_usd(stats.avg_win)}{abs(stats.avg_win):.2f} / {stats.avg_mfe_pct:+.2f}%",
                    C_GOOD,
                ),
                Metric(
                    "Avg Loss / MAE (on TPs)",
                    f"{get_usd(stats.avg_loss)}{abs(stats.avg_loss):.2f} / {stats.avg_mae_pct:+.2f}%",
                    C_BAD,
                ),
                Metric(
                    "Avg Position Hold Time",
                    f"{stats.avg_hold_time_positions:.1f} min",
                ),
            ],
        ),
    ]


def _distribute(sections: list[Section], columns: int) -> list[list[Section]]:
    """Greedy: put each section (in order) into the currently shortest column."""
    cols: list[list[Section]] = [[] for _ in range(columns)]
    heights: list[int] = [0] * columns
    for sec in sections:
        i: int = heights.index(min(heights))
        cols[i].append(sec)
        heights[i] += sec.height
    return cols


def plot_info_dashboard(stats: Stats, columns: int = 2) -> Figure:
    if not stats.trades_close:
        return empty_figure()

    columns = max(1, columns)
    cols: list[list[Section]] = _distribute(build_sections(stats), columns)
    content_h: int = max(sum(s.height for s in col) for col in cols)
    height: int = TOP_PAD + content_h + BOTTOM_PAD

    fig = Figure()
    shapes: list[dict[str, object]] = []
    annotations: list[dict[str, object]] = []

    col_w: float = 1.0 - COL_GAP
    for ci, col in enumerate(cols):
        x0: float = ci + COL_GAP / 2
        x1: float = x0 + col_w
        y: float = 0.0
        for sec in col:
            # Section header band
            shapes.append(
                {
                    "type": "rect",
                    "xref": "x",
                    "yref": "y",
                    "x0": x0,
                    "x1": x1,
                    "y0": y,
                    "y1": y + SECTION_H,
                    "fillcolor": C_HEADER_BG,
                    "line": {"color": C_BORDER, "width": 1},
                    "layer": "below",
                }
            )
            annotations.append(
                {
                    "x": x0 + 0.015,
                    "y": y + SECTION_H / 2,
                    "xref": "x",
                    "yref": "y",
                    "text": f"<b>{sec.title}</b>",
                    "showarrow": False,
                    "xanchor": "left",
                    "yanchor": "middle",
                    "font": {"color": C_ACCENT, "size": 15, "family": FONT},
                }
            )
            y += SECTION_H
            for ri, m in enumerate(sec.metrics):
                shapes.append(
                    {
                        "type": "rect",
                        "xref": "x",
                        "yref": "y",
                        "x0": x0,
                        "x1": x1,
                        "y0": y,
                        "y1": y + ROW_H,
                        "fillcolor": C_ROW_A if ri % 2 == 0 else C_ROW_B,
                        "line": {"width": 0},
                        "layer": "below",
                    }
                )
                annotations.append(
                    {
                        "x": x0 + 0.015,
                        "y": y + ROW_H / 2,
                        "xref": "x",
                        "yref": "y",
                        "text": m.label,
                        "showarrow": False,
                        "xanchor": "left",
                        "yanchor": "middle",
                        "font": {"color": C_TEXT, "size": 14, "family": FONT},
                    }
                )
                annotations.append(
                    {
                        "x": x1 - 0.015,
                        "y": y + ROW_H / 2,
                        "xref": "x",
                        "yref": "y",
                        "text": f"<b>{m.value}</b>",
                        "showarrow": False,
                        "xanchor": "right",
                        "yanchor": "middle",
                        "font": {"color": m.color, "size": 14, "family": FONT},
                    }
                )
                y += ROW_H
            y += SECTION_GAP

    fig.update_layout(  # pyright: ignore[reportUnknownMemberType]
        shapes=shapes,
        annotations=annotations,
        height=height,
        hovermode=False,
        showlegend=False,
    )
    fig.update_xaxes(  # pyright: ignore[reportUnknownMemberType]
        range=[0, columns],
        visible=False,
        fixedrange=True,
    )
    fig.update_yaxes(  # pyright: ignore[reportUnknownMemberType]
        range=[content_h, 0],  # inverted: row 0 on top
        visible=False,
        fixedrange=True,
    )

    # apply_dark_theme re-enables axis lines; hide them again afterwards.
    fig = apply_dark_theme(
        fig, f"SYSTEM PERFORMANCE & QUANTITATIVE KPI ({stats.symbol})"
    )
    fig.update_layout(  # pyright: ignore[reportUnknownMemberType]
        margin={"l": 30, "r": 30, "t": TOP_PAD, "b": BOTTOM_PAD}
    )
    fig.update_xaxes(visible=False)  # pyright: ignore[reportUnknownMemberType]
    fig.update_yaxes(visible=False)  # pyright: ignore[reportUnknownMemberType]
    return fig
