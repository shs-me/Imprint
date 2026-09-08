from plotly.graph_objects import (  # pyright: ignore[reportMissingTypeStubs]
    Figure,
    Histogram,
)

from imprint.visualization.analyze import Stats
from imprint.visualization.plot.utils import apply_dark_theme, empty_figure


def plot_trade_distribution(stats: Stats) -> Figure:
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

    fig: Figure = Figure()

    # Precise bin size of 0.1% for precise detail visibility
    bin_config: dict[str, float] = {"start": -20.0, "end": 20.0, "size": 0.1}

    # TP & SL & MAE & MFE Disttribution
    for pnl_pcts, name, legend, color, opacity, hovertemplate in zip(
        [p_pnls, l_pnls, maes, mfes],
        [
            "TP (Realized Profit)",
            "SL (Realized Loss)",
            "MAE (Adverse Runup)",
            "MFE (Favorable Runup)",
        ],
        ["legend", "legend2", "legend2", "legend"],
        ["#009600", "#960000", "#960000", "#009600"],
        [0.5, 0.5, 1.0, 1.0],
        [
            "TP: %{y:.2f}%<br>Count: %{x}<extra></extra>",
            "SL: %{y:.2f}%<br>Count: %{x}<extra></extra>",
            "MAE: %{y:.2f}%<br>Count: %{x}<extra></extra>",
            "MFE: %{y:.2f}%<br>Count: %{x}<extra></extra>",
        ],
    ):
        fig.add_trace(  # pyright: ignore[reportUnknownMemberType]
            Histogram(
                y=pnl_pcts,
                name=name,
                legend=legend,
                marker_color=color,
                marker_line_width=0.5,
                marker_line_color="#FFFFFF",
                opacity=opacity,
                orientation="h",
                ybins=bin_config,
                hovertemplate=hovertemplate,
            )
        )

    # Entry Position Line
    fig.add_hline(  # pyright: ignore[reportUnknownMemberType]
        y=0, line_width=1.5, line_color="#ECEFF1", opacity=0.8
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
