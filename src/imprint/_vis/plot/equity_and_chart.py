"""Synchronized equity and candlestick price chart rendering module."""

from typing import Any

import numpy as np
from numpy import float64
from plotly.graph_objects import (  # pyright: ignore[reportMissingTypeStubs]
    Figure,
)
from plotly.subplots import (  # pyright: ignore[reportMissingTypeStubs]
    make_subplots,  # pyright: ignore[reportUnknownVariableType]
)

from imprint._vis.analyze import Stats, build_resampled_timeframes
from imprint._vis.analyze.resample import BAR_THRESHOLD
from imprint._vis.plot.chart import add_chart_traces
from imprint._vis.plot.equity import add_equity_traces
from imprint._vis.plot.utils import apply_dark_theme, empty_figure
from imprint._vis.settings import ResampledData


def _get_144_bounds(
    tf_data: ResampledData, base_b: float, base_p: float64
) -> dict[str, Any]:
    times = tf_data["ohlc"]["time"]
    n: int = len(times)
    s = slice(-BAR_THRESHOLD, None) if n > BAR_THRESHOLD else slice(None)

    x0: str = str(times[-BAR_THRESHOLD]) if n > BAR_THRESHOLD else str(times[0])
    x1: str = str(times[-1])

    p_lo: float = float(np.min(tf_data["ohlc"]["low"][s]))
    p_hi: float = float(np.max(tf_data["ohlc"]["high"][s]))
    p_pad: float = (p_hi - p_lo) * 0.04 or 1.0

    eq_lo: float = min(float(np.min(tf_data["eq_low"])), base_b)
    eq_hi: float = max(float(np.max(tf_data["eq_high"])), base_b)
    eq_pad: float = (eq_hi - eq_lo) * 0.05 or 1.0

    rp_lo: float = (p_lo - base_p) / base_p * 100.0
    rp_hi: float = (p_hi - base_p) / base_p * 100.0
    rp_pad: float = (rp_hi - rp_lo) * 0.04 or 0.1

    req_lo: float = (eq_lo - eq_pad - base_b) / base_b * 100.0
    req_hi: float = (eq_hi + eq_pad - base_b) / base_b * 100.0

    return {
        "x": [x0, x1],
        "p": [p_lo - p_pad, p_hi + p_pad],
        "eq": [eq_lo - eq_pad, eq_hi + eq_pad],
        "rp": [rp_lo - rp_pad, rp_hi + rp_pad],
        "req": [req_lo, req_hi],
    }


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

    base_p: float64 = stats.ohlc["close"][0]
    base_b: float = stats.start_balance
    init_b = _get_144_bounds(tf_series[0], base_b, base_p)

    buttons: list[dict[str, Any]] = []
    if len(tf_series) > 1:
        for target_k, tf_data in enumerate(tf_series):
            vis: list[bool] = [
                (t_idx is None or t_idx == target_k) for t_idx in trace_tf_map
            ]
            buttons.append(
                {
                    "label": tf_data["timeframe_name"],
                    "method": "restyle",
                    "args": [{"visible": vis}],
                }
            )

    base_axis: dict[str, Any] = {
        "ticks": "outside",
        "ticklen": 6,
        "tickfont": {"size": 11, "color": "#CFD8DC"},
        "showline": True,
        "linecolor": "#424242",
    }

    def make_left_axis(
        title: str, fmt: str, y_range: list[float], fixed: bool = False
    ) -> dict[str, Any]:
        return {
            **base_axis,
            "title_text": title,
            "title_standoff": 8,
            "showgrid": True,
            "tickformat": fmt,
            "mirror": True,
            "range": y_range,
            "fixedrange": fixed,
        }

    def make_right_axis(y_range: list[float]) -> dict[str, Any]:
        return {
            **base_axis,
            "title_text": "",
            "side": "right",
            "ticksuffix": "%",
            "tickformat": "+.1f",
            "showgrid": False,
            "range": y_range,
            "fixedrange": True,
        }

    fig.update_layout(  # pyright: ignore[reportUnknownMemberType]
        autosize=True,
        margin={"l": 45, "r": 45, "t": 32, "b": 22},
        yaxis=make_left_axis(
            "Balance (Left $ | Right %)", ",.0f", init_b["eq"], fixed=True
        ),
        yaxis2=make_right_axis(init_b["req"]),
        yaxis3=make_left_axis(
            "Price (Left $ | Right %)", ",.2f", init_b["p"], fixed=False
        ),
        yaxis4=make_right_axis(init_b["rp"]),
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

    if buttons:
        fig.update_layout(  # pyright: ignore[reportUnknownMemberType]
            updatemenus=[
                {
                    "type": "buttons",
                    "direction": "right",
                    "active": 0,
                    "showactive": False,
                    "x": 0.0,
                    "xanchor": "left",
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
                    "buttons": buttons,
                }
            ]
        )

    fig.update_xaxes(  # pyright: ignore[reportUnknownMemberType]
        range=init_b["x"],
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
