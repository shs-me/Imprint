from plotly.graph_objects import (  # pyright: ignore[reportMissingTypeStubs]
    Candlestick,
    Figure,
    Scatter,
)

from imprint._vis.analyze import Stats
from imprint._vis.plot.utils import apply_dark_theme, empty_figure
from imprint._vis.settings import CloseTrades


def plot_trade_distribution(stats: Stats) -> Figure:
    if not stats.trades_close:
        return empty_figure()

    trades: list[CloseTrades] = stats.trades_close
    total_trades: int = len(trades)

    trade_indices: list[int] = list(range(1, total_trades + 1))

    open_pct: list[float] = [0.0] * total_trades
    close_pct: list[float] = []
    high_pct: list[float] = []
    low_pct: list[float] = []

    planned_tp: list[float] = []
    planned_sl: list[float] = []

    hover_texts: list[str] = []

    for idx, tc in enumerate(trades, start=1):
        close_pct.append(tc["pnl_pct"])
        high_pct.append(max(tc["mfe_pct"], tc["pnl_pct"], 0.0))
        low_pct.append(min(tc["mae_pct"], tc["pnl_pct"], 0.0))

        planned_tp.append(tc["planned_tp_pct"])
        planned_sl.append(tc["planned_sl_pct"])

        hover_texts.append(
            f"<b>Trade #{idx} ({'LONG' if tc['is_long'] else 'SHORT'})</b><br>"
            + f"Time: {tc['time']}<br>"
            + f"Realized PnL: {tc['pnl_pct']:+.2f}% (${tc['pnl']:,.2f})<br>"
            + f"Runup (MFE): +{tc['mfe_pct']:.2f}%<br>"
            + f"Drawdown (MAE): {tc['mae_pct']:.2f}%<br>"
            + f"Balance: ${tc['balance']:,.2f}"
        )

    fig = Figure()

    # 1. Trade Candlestick (OHLC)
    fig.add_trace(  # pyright: ignore[reportUnknownMemberType]
        Candlestick(
            x=trade_indices,
            open=open_pct,
            high=high_pct,
            low=low_pct,
            close=close_pct,
            name="Trade Excursion",
            increasing_line_color="#00E676",
            increasing_fillcolor="rgba(0, 230, 118, 0.4)",
            decreasing_line_color="#FF1744",
            decreasing_fillcolor="rgba(255, 23, 68, 0.4)",
            text=hover_texts,
            hoverinfo="text",
        )
    )

    # 2. Planned TP markers
    fig.add_trace(  # pyright: ignore[reportUnknownMemberType]
        Scatter(
            x=trade_indices,
            y=planned_tp,
            mode="lines",
            name="Planned TP Target",
            line={"color": "#78909C", "dash": "dash", "width": 1.2},
            opacity=0.7,
            hovertemplate="Planned TP: %{y:.2f}%<extra></extra>",
        )
    )

    # 3. Planned SL markers
    fig.add_trace(  # pyright: ignore[reportUnknownMemberType]
        Scatter(
            x=trade_indices,
            y=planned_sl,
            mode="lines",
            name="Planned SL Target",
            line={"color": "#78909C", "dash": "dash", "width": 1.2},
            opacity=0.7,
            hovertemplate="Planned SL: %{y:.2f}%<extra></extra>",
        )
    )

    # Zero reference baseline
    fig.add_hline(  # pyright: ignore[reportUnknownMemberType]
        y=0,
        line_width=1.2,
        line_color="#78909C",
        line_dash="dash",
        opacity=0.7,
    )

    # Chart layout setup
    fig.update_layout(  # pyright: ignore[reportUnknownMemberType]
        hovermode="closest",
        showlegend=False,
        margin={"l": 55, "r": 40, "t": 45, "b": 35},
    )

    x_start: float = max(0.5, total_trades - 99.5)
    x_end: float = total_trades + 0.5

    # Axis properties
    fig.update_xaxes(  # pyright: ignore[reportUnknownMemberType]
        title_text="Trade Sequence Number (#)",
        range=[x_start, x_end],
        rangeslider={
            "visible": True,
            "thickness": 0.08,
            "bgcolor": "#1A2327",
            "bordercolor": "#37474F",
            "borderwidth": 1,
        },
        ticks="outside",
        ticklen=6,
        tickfont={"size": 11, "color": "#CFD8DC"},
        showgrid=True,
        dtick=5 if total_trades > 50 else 1,
    )

    fig.update_yaxes(  # pyright: ignore[reportUnknownMemberType]
        title_text="Price Deviation (%) [0 = Entry]",
        ticksuffix="%",
        ticks="outside",
        ticklen=6,
        tickfont={"size": 11, "color": "#CFD8DC"},
        showgrid=True,
        zeroline=False,
    )

    return apply_dark_theme(
        fig, "TRADE EXCURSION CANDLES: MAE / MFE / PNL & PLANNED TARGETS"
    )
