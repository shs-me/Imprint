from typing import Any

from plotly.graph_objects import (  # pyright: ignore[reportMissingTypeStubs]
    Figure,
)
from plotly.subplots import (  # pyright: ignore[reportMissingTypeStubs]
    make_subplots,  # pyright: ignore[reportUnknownVariableType]
)

from imprint._vis.analyze import Stats, build_resampled_timeframes
from imprint._vis.plot.chart import add_chart_traces
from imprint._vis.plot.equity import add_equity_traces
from imprint._vis.plot.utils import apply_dark_theme, empty_figure
from imprint._vis.settings import ResampledData


def plot_equity_and_chart(stats: Stats) -> Figure:
    if len(stats.eq_times) == 0 or len(stats.ohlc["time"]) == 0:
        return empty_figure()

    fig: Figure = make_subplots(
        rows=2,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.03,
        row_heights=[0.33, 0.67],
        specs=[[{"secondary_y": True}], [{"secondary_y": True}]],
        subplot_titles=[
            "DYNAMIC EQUITY & DRAWDOWN & PRICE & TRADE EXECUTIONS",
            "",
        ],
    )

    tf_series: list[ResampledData] = build_resampled_timeframes(
        ohlc=stats.ohlc,
        eq_times=stats.eq_times,
        eq_open=stats.eq_open,
        eq_high=stats.eq_high,
        eq_low=stats.eq_low,
        eq_close=stats.eq_close,
        start_balance=stats.start_balance,
        base_tf_ms=stats.timeframe,
        dynamic_drawdowns=stats.dynamic_drawdowns,
    )

    trace_tf_map: list[int | None] = []

    add_equity_traces(fig, stats, tf_series, trace_tf_map)
    add_chart_traces(fig, stats, tf_series, trace_tf_map)

    all_times = stats.ohlc["time"]
    x_end: str = str(all_times[-1])
    x_full_start: str = str(all_times[0])
    x_start_144: str = (
        str(all_times[-144]) if len(all_times) > 144 else x_full_start
    )

    # Timeframe Buttons
    buttons: list[dict[str, Any]] = []
    if len(tf_series) > 1:
        for target_k, tf_data in enumerate(tf_series):
            visibility_vector: list[bool] = [
                (t_idx is None or t_idx == target_k) for t_idx in trace_tf_map
            ]
            buttons.append(
                {
                    "label": tf_data["timeframe_name"],
                    "method": "update",
                    "args": [{"visible": visibility_vector}],
                }
            )

    # Common layout styles for y-axes
    base_axis = {
        "ticks": "outside",
        "ticklen": 6,
        "tickfont": {"size": 11, "color": "#CFD8DC"},
        "showline": True,
        "linecolor": "#424242",
    }

    def make_left_axis(title: str, fmt: str) -> dict[str, Any]:
        return {
            **base_axis,
            "title_text": title,
            "title_standoff": 8,
            "showgrid": True,
            "tickformat": fmt,
            "mirror": True,
        }

    def make_right_axis() -> dict[str, Any]:
        return {
            **base_axis,
            "title_text": "",
            "side": "right",
            "ticksuffix": "%",
            "tickformat": "+.1f",
            "showgrid": False,
        }

    fig.update_layout(  # pyright: ignore[reportUnknownMemberType]
        autosize=True,
        margin={"l": 45, "r": 45, "t": 32, "b": 22},
        yaxis=make_left_axis("Balance (Left $ | Right %)", ",.0f"),
        yaxis2=make_right_axis(),
        yaxis3=make_left_axis("Price (Left $ | Right %)", ",.2f"),
        yaxis4=make_right_axis(),
        yaxis5={  # Right Dynamic Drawdown In Equity
            "title": "",
            "tickfont": {"color": "#FF5252", "size": 10},
            "ticksuffix": "%",
            "overlaying": "y",
            "side": "right",
            "range": [-min(100, abs(stats.max_dd_pct * 3)), 0.0],
            "showgrid": False,
            "zeroline": True,
            "zerolinecolor": "rgba(255, 23, 68, 0.4)",
            "zerolinewidth": 1,
            "showticklabels": True,
            "ticklabelposition": "inside",
            "fixedrange": True,
        },
        legend={  # Legend Equity
            "orientation": "h",
            "x": 0.01,
            "y": 0.70,
            "xanchor": "left",
            "yanchor": "bottom",
            "bgcolor": "rgba(18, 18, 18, 0.75)",
            "bordercolor": "#37474F",
            "borderwidth": 1,
            "font": {
                "size": 10,
                "family": "'Courier New', Consolas, monospace",
                "color": "#CFD8DC",
            },
        },
        legend2={  # Legend Chart
            "orientation": "h",
            "x": 0.01,
            "y": 0.64,
            "xanchor": "left",
            "yanchor": "top",
            "bgcolor": "rgba(18, 18, 18, 0.75)",
            "bordercolor": "#37474F",
            "borderwidth": 1,
            "font": {
                "size": 10,
                "family": "'Courier New', Consolas, monospace",
                "color": "#CFD8DC",
            },
        },
    )

    # Common styling helper for updatemenu buttons
    def make_updatemenu(
        x: float, xanchor: str, buttons_list: list[dict[str, Any]]
    ) -> dict[str, Any]:
        return {
            "type": "buttons",
            "direction": "right",
            "active": 0,
            "showactive": False,
            "x": x,
            "xanchor": xanchor,
            "y": 1.05,
            "yanchor": "bottom",
            "bgcolor": "#1E1E1E",
            "bordercolor": "#37474F",
            "borderwidth": 1,
            "pad": {"r": 4, "t": 2, "b": 2},
            "font": {
                "color": "#00E5FF",
                "size": 10,
                "family": "'Courier New', Consolas, monospace",
            },
            "buttons": buttons_list,
        }

    updatemenus_list: list[dict[str, Any]] = []
    if buttons:
        updatemenus_list.append(make_updatemenu(0.0, "left", buttons))

    updatemenus_list.append(
        make_updatemenu(
            1.0,
            "right",
            [
                {
                    "label": "144 Bars",
                    "method": "relayout",
                    "args": [
                        {
                            "xaxis.range": [x_start_144, x_end],
                            "xaxis2.range": [x_start_144, x_end],
                            "xaxis.autorange": False,
                            "xaxis2.autorange": False,
                        }
                    ],
                },
                {
                    "label": "ALL",
                    "method": "relayout",
                    "args": [
                        {
                            "xaxis.range": [x_full_start, x_end],
                            "xaxis2.range": [x_full_start, x_end],
                            "xaxis.autorange": False,
                            "xaxis2.autorange": False,
                        }
                    ],
                },
            ],
        )
    )

    fig.update_layout(  # pyright: ignore[reportUnknownMemberType]
        updatemenus=updatemenus_list
    )

    fig.update_xaxes(  # pyright: ignore[reportUnknownMemberType]
        range=[x_start_144, x_end],
        ticks="outside",
        ticklen=6,
        tickfont={"size": 11, "color": "#CFD8DC"},
        rangeslider={"visible": False},
        showgrid=True,
    )

    fig = apply_dark_theme(fig, title="")

    for annotation in fig["layout"]["annotations"]:  # pyright: ignore[reportUnknownVariableType]
        if (
            annotation["text"]  # pyright: ignore[reportArgumentType, reportCallIssue]
            == "DYNAMIC EQUITY & DRAWDOWN & PRICE & TRADE EXECUTIONS"
        ):
            annotation["font"] = {  # pyright: ignore[reportIndexIssue]
                "size": 13,
                "color": "#ECEFF1",
                "family": "'Courier New', Consolas, monospace",
            }
            annotation["yshift"] = 10  # pyright: ignore[reportIndexIssue]

    return fig
