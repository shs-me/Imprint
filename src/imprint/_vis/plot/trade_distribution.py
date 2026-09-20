from plotly.graph_objects import (  # pyright: ignore[reportMissingTypeStubs]
    Figure,
    Scatter,
)

from imprint._vis.analyze import Stats
from imprint._vis.plot.utils import apply_dark_theme, empty_figure


def plot_trade_distribution(stats: Stats) -> Figure:
    if not stats.trades_close:
        return empty_figure()

    # Data containers for scatter markers
    tp_x: list[int] = []
    tp_y: list[float] = []
    tp_hover: list[str] = []

    mae_x: list[int] = []
    mae_y: list[float] = []
    mae_hover: list[str] = []

    sl_x: list[int] = []
    sl_y: list[float] = []
    sl_hover: list[str] = []

    mfe_x: list[int] = []
    mfe_y: list[float] = []
    mfe_hover: list[str] = []

    # Excursion connecting stems
    win_stem_x: list[int | None] = []
    win_stem_y: list[float | None] = []
    loss_stem_x: list[int | None] = []
    loss_stem_y: list[float | None] = []

    # Process closed trades by sequence index
    for trade_no, tc in enumerate(stats.trades_close, start=1):
        t = tc["time"]
        pnl = tc["pnl"]
        pnl_pct = tc["pnl_pct"]
        side = "Long" if tc["is_long"] else "Short"
        price = tc["price"]
        balance = tc["balance"]
        mae_pct = tc["mae_pct"]
        mfe_pct = tc["mfe_pct"]

        if pnl_pct >= 0:
            # Winning trade (TP)
            tp_x.append(trade_no)
            tp_y.append(pnl_pct)
            tp_hover.append(
                f"<b>Take Profit (Trade #{trade_no})</b><br>"
                + f"Time: {t}<br>"
                + f"Side: {side} | Exit Price: ${price:,.2f}<br>"
                + f"Realized PnL: +${pnl:,.2f} (+{pnl_pct:.2f}%)<br>"
                + f"Drawdown Endured (MAE): {mae_pct:.2f}%<br>"
                + f"Balance: ${balance:,.2f}"
            )

            # Adverse excursion during win (MAE)
            mae_x.append(trade_no)
            mae_y.append(mae_pct)
            mae_hover.append(
                f"<b>MAE on Win (Trade #{trade_no})</b><br>"
                + f"Time: {t}<br>"
                + f"Side: {side}<br>"
                + f"Max Adverse Excursion: {mae_pct:.2f}%<br>"
                + f"Final PnL: +${pnl:,.2f} (+{pnl_pct:.2f}%)"
            )

            win_stem_x.extend([trade_no, trade_no, None])
            win_stem_y.extend([mae_pct, pnl_pct, None])

        else:
            # Losing trade (SL)
            sl_x.append(trade_no)
            sl_y.append(pnl_pct)
            sl_hover.append(
                f"<b>Stop Loss (Trade #{trade_no})</b><br>"
                + f"Time: {t}<br>"
                + f"Side: {side} | Exit Price: ${price:,.2f}<br>"
                + f"Realized PnL: -${abs(pnl):,.2f} ({pnl_pct:.2f}%)<br>"
                + f"Peak Runup (MFE): +{mfe_pct:.2f}%<br>"
                + f"Balance: ${balance:,.2f}"
            )

            # Favorable excursion before stop (MFE)
            mfe_x.append(trade_no)
            mfe_y.append(mfe_pct)
            mfe_hover.append(
                f"<b>MFE on Stop (Trade #{trade_no})</b><br>"
                + f"Time: {t}<br>"
                + f"Side: {side}<br>"
                + f"Max Favorable Excursion: +{mfe_pct:.2f}%<br>"
                + f"Final Loss: -${abs(pnl):,.2f} ({pnl_pct:.2f}%)"
            )

            loss_stem_x.extend([trade_no, trade_no, None])
            loss_stem_y.extend([pnl_pct, mfe_pct, None])

    fig: Figure = Figure()

    # Background excursion stems
    if win_stem_x:
        fig.add_trace(  # pyright: ignore[reportUnknownMemberType]
            Scatter(
                x=win_stem_x,
                y=win_stem_y,
                mode="lines",
                line={
                    "color": "rgba(0, 230, 118, 0.22)",
                    "width": 1.2,
                    "dash": "dot",
                },
                showlegend=False,
                hoverinfo="skip",
            )
        )

    if loss_stem_x:
        fig.add_trace(  # pyright: ignore[reportUnknownMemberType]
            Scatter(
                x=loss_stem_x,
                y=loss_stem_y,
                mode="lines",
                line={
                    "color": "rgba(255, 23, 68, 0.22)",
                    "width": 1.2,
                    "dash": "dot",
                },
                showlegend=False,
                hoverinfo="skip",
            )
        )

    # Realized TP markers
    if tp_x:
        fig.add_trace(  # pyright: ignore[reportUnknownMemberType]
            Scatter(
                x=tp_x,
                y=tp_y,
                mode="markers",
                name="TP (Realized Profit)",
                marker={
                    "color": "#00E676",
                    "size": 8,
                    "symbol": "circle",
                    "line": {"color": "#FFFFFF", "width": 0.8},
                },
                hovertext=tp_hover,
                hoverinfo="text",
            )
        )

    # MFE on stop markers
    if mfe_x:
        fig.add_trace(  # pyright: ignore[reportUnknownMemberType]
            Scatter(
                x=mfe_x,
                y=mfe_y,
                mode="markers",
                name="MFE (Runup on Stop)",
                marker={
                    "color": "rgba(76, 175, 80, 0.65)",
                    "size": 6,
                    "symbol": "diamond",
                    "line": {"color": "#4CAF50", "width": 1.0},
                },
                hovertext=mfe_hover,
                hoverinfo="text",
            )
        )

    # Realized SL markers
    if sl_x:
        fig.add_trace(  # pyright: ignore[reportUnknownMemberType]
            Scatter(
                x=sl_x,
                y=sl_y,
                mode="markers",
                name="SL (Realized Loss)",
                marker={
                    "color": "#FF1744",
                    "size": 8,
                    "symbol": "circle",
                    "line": {"color": "#FFFFFF", "width": 0.8},
                },
                hovertext=sl_hover,
                hoverinfo="text",
            )
        )

    # MAE on take markers
    if mae_x:
        fig.add_trace(  # pyright: ignore[reportUnknownMemberType]
            Scatter(
                x=mae_x,
                y=mae_y,
                mode="markers",
                name="MAE (Drawdown on Take)",
                marker={
                    "color": "rgba(239, 83, 80, 0.65)",
                    "size": 6,
                    "symbol": "diamond",
                    "line": {"color": "#EF5350", "width": 1.0},
                },
                hovertext=mae_hover,
                hoverinfo="text",
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
        margin={"l": 55, "r": 40, "t": 45, "b": 35},
        legend={
            "orientation": "h",
            "x": 0.5,
            "xanchor": "center",
            "y": 1.06,
            "yanchor": "bottom",
            "bgcolor": "rgba(18, 18, 18, 0.85)",
            "bordercolor": "#37474F",
            "borderwidth": 1,
            "font": {
                "size": 10,
                "family": "'Courier New', Consolas, monospace",
                "color": "#CFD8DC",
            },
        },
    )

    total_trades = len(stats.trades_close)

    # Axis properties
    fig.update_xaxes(  # pyright: ignore[reportUnknownMemberType]
        title_text="Trade Sequence Number (#)",
        ticks="outside",
        ticklen=6,
        tickfont={"size": 11, "color": "#CFD8DC"},
        showgrid=True,
        range=[0.5, total_trades + 0.5],
        dtick=1 if total_trades <= 30 else (5 if total_trades <= 100 else None),
    )

    fig.update_yaxes(  # pyright: ignore[reportUnknownMemberType]
        title_text="Price Deviation / PnL (%)",
        ticksuffix="%",
        ticks="outside",
        ticklen=6,
        tickfont={"size": 11, "color": "#CFD8DC"},
        showgrid=True,
        zeroline=False,
    )

    return apply_dark_theme(fig, "TRADE SEQUENCE: PNL & MAE & MFE EXCURSIONS")
