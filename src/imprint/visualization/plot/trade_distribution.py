import plotly.graph_objects as go  # pyright: ignore[reportMissingTypeStubs]

from imprint.visualization.analyze import Stats
from imprint.visualization.plot.utils import apply_dark_theme, empty_figure


def plot_trade_distribution(stats: Stats) -> go.Figure:
    if not stats.trades_close:
        return empty_figure()

    p_pnls: list[float] = [
        tc["pnl_pct"] for tc in stats.trades_close if tc["pnl_pct"] > 0
    ]
    l_pnls: list[float] = [
        tc["pnl_pct"] for tc in stats.trades_close if tc["pnl_pct"] < 0
    ]
    maes: list[float] = [
        tc["mae_pct"] for tc in stats.trades_close if tc["mae_pct"] < 0
    ]
    mfes: list[float] = [
        tc["mfe_pct"] for tc in stats.trades_close if tc["mfe_pct"] > 0
    ]

    fig: go.Figure = go.Figure()

    # Precise bin size of 0.1% for precise detail visibility
    bin_config = {"start": -20.0, "end": 20.0, "size": 0.1}

    # Bottom Layers (Solid / Opaque Base): MAE & MFE
    # MAE: Adverse movement during TP/profit trades
    if maes:
        fig.add_trace(  # pyright: ignore[reportUnknownMemberType]
            go.Histogram(
                y=maes,
                name="MAE (Adverse Runup)",
                legend="legend2",
                marker_color="#C62828",
                marker_line_width=0.5,
                marker_line_color="#121212",
                opacity=1.0,
                orientation="h",
                ybins=bin_config,
                hovertemplate="MAE: %{y:.2f}%<br>Count: %{x}<extra></extra>",
            )
        )

    # MFE: Favorable movement during SL/loss trades
    if mfes:
        fig.add_trace(  # pyright: ignore[reportUnknownMemberType]
            go.Histogram(
                y=mfes,
                name="MFE (Favorable Runup)",
                legend="legend",
                marker_color="#00E676",
                marker_line_width=0.5,
                marker_line_color="#121212",
                opacity=1.0,
                orientation="h",
                ybins=bin_config,
                hovertemplate="MFE: %{y:.2f}%<br>Count: %{x}<extra></extra>",
            )
        )

    # Top Layers (Closed outcome overlays on top): TP & SL
    # TP (Take Profit closed trades)
    if p_pnls:
        fig.add_trace(  # pyright: ignore[reportUnknownMemberType]
            go.Histogram(
                y=p_pnls,
                name="TP (Realized Profit)",
                legend="legend",
                marker_color="#0D5233",
                marker_line_width=0.5,
                marker_line_color="#121212",
                opacity=0.95,
                orientation="h",
                ybins=bin_config,
                hovertemplate="TP: %{y:.2f}%<br>Count: %{x}<extra></extra>",
            )
        )

    # SL (Stop Loss closed trades)
    if l_pnls:
        fig.add_trace(  # pyright: ignore[reportUnknownMemberType]
            go.Histogram(
                y=l_pnls,
                name="SL (Realized Loss)",
                legend="legend2",
                marker_color="#521220",
                marker_line_width=0.5,
                marker_line_color="#121212",
                opacity=0.95,
                orientation="h",
                ybins=bin_config,
                hovertemplate="SL: %{y:.2f}%<br>Count: %{x}<extra></extra>",
            )
        )

    fig.add_hline(  # pyright: ignore[reportUnknownMemberType]
        y=0,
        line_width=1.5,
        line_color="#ECEFF1",
        opacity=0.8,
    )

    fig.update_layout(  # pyright: ignore[reportUnknownMemberType]
        barmode="overlay",
        bargap=0.03,
        margin={"l": 60, "r": 40, "t": 35, "b": 35},
        legend={  # TP / MFE
            "orientation": "h",
            "x": 0.99,
            "xanchor": "right",
            "y": 0.52,
            "yanchor": "bottom",
            "bgcolor": "rgba(18, 18, 18, 0.85)",
            "bordercolor": "#1B5E20",
            "borderwidth": 1,
            "font": {
                "size": 10,
                "family": "'Courier New', Consolas, monospace",
                "color": "#CFD8DC",
            },
        },
        legend2={  # SL / MAE
            "orientation": "h",
            "x": 0.99,
            "xanchor": "right",
            "y": 0.48,
            "yanchor": "top",
            "bgcolor": "rgba(18, 18, 18, 0.85)",
            "bordercolor": "#B71C1C",
            "borderwidth": 1,
            "font": {
                "size": 10,
                "family": "'Courier New', Consolas, monospace",
                "color": "#CFD8DC",
            },
        },
    )
    fig.update_xaxes(  # pyright: ignore[reportUnknownMemberType]
        title_text="Trade Count",
        ticks="outside",
        ticklen=6,
        tickfont={"size": 11, "color": "#CFD8DC"},
        showgrid=True,
    )
    fig.update_yaxes(  # pyright: ignore[reportUnknownMemberType]
        title_text="Price Deviation From Entry (%)",
        ticksuffix="%",
        ticks="outside",
        ticklen=6,
        tickfont={"size": 11, "color": "#CFD8DC"},
        showgrid=True,
    )

    return apply_dark_theme(fig, "TRADE PNL & MAE & MFE DISTRIBUTION")
