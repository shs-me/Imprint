import numpy as np
from numpy import datetime64, float64
from plotly.graph_objects import (  # pyright: ignore[reportMissingTypeStubs]
    Candlestick,
    Figure,
    Scatter,
)

from imprint.visualization.analyze import Stats
from imprint.visualization.settings import (
    CloseTrades,
    OpenTrades,
    ResampledData,
)


def _group_open_trades(
    trades: list[OpenTrades], tf_ms: int, is_long: bool
) -> tuple[list[datetime64], list[float], list[str]]:
    filtered = [t for t in trades if t["is_long"] == is_long]
    if not filtered:
        return [], [], []

    buckets: dict[int, list[OpenTrades]] = {}
    for t in filtered:
        t_ms = int(t["time"].timestamp() * 1000)
        bucket = (t_ms // tf_ms) * tf_ms
        buckets.setdefault(bucket, []).append(t)

    times: list[datetime64] = []
    prices: list[float] = []
    hover_texts: list[str] = []
    side = "Long" if is_long else "Short"

    for b_ms, group in buckets.items():
        times.append(np.datetime64(b_ms, "ms"))
        avg_price = float(np.mean([item["price"] for item in group]))
        prices.append(avg_price)
        count = len(group)
        if count == 1:
            hover_texts.append(
                f"Entry {side}: ${avg_price:,.2f}<br>Time: {np.datetime64(b_ms, 'ms')}"
            )
        else:
            hover_texts.append(
                f"Entry {side} (x{count}): avg ${avg_price:,.2f}<br>Time: {np.datetime64(b_ms, 'ms')}"
            )

    return times, prices, hover_texts


def _group_close_trades(
    trades: list[CloseTrades], tf_ms: int, is_long: bool
) -> tuple[list[datetime64], list[float], list[str]]:
    filtered = [t for t in trades if t["is_long"] == is_long]
    if not filtered:
        return [], [], []

    buckets: dict[int, list[CloseTrades]] = {}
    for t in filtered:
        t_ms = int(t["time"].timestamp() * 1000)
        bucket = (t_ms // tf_ms) * tf_ms
        buckets.setdefault(bucket, []).append(t)

    times: list[datetime64] = []
    prices: list[float] = []
    hover_texts: list[str] = []
    side = "Long" if is_long else "Short"

    for b_ms, group in buckets.items():
        times.append(np.datetime64(b_ms, "ms"))
        avg_price: float = float(np.mean([item["price"] for item in group]))
        prices.append(avg_price)
        total_pnl: float = float(np.sum([item["pnl"] for item in group]))
        avg_pnl_pct: float = float(np.mean([item["pnl_pct"] for item in group]))
        count: int = len(group)
        if count == 1:
            hover_texts.append(
                f"Close {side}: ${avg_price:,.2f}<br>PnL: ${total_pnl:,.2f} ({avg_pnl_pct:+.2f}%)<br>Time: {np.datetime64(b_ms, 'ms')}"
            )
        else:
            hover_texts.append(
                f"Close {side} (x{count}): avg ${avg_price:,.2f}<br>Total PnL: ${total_pnl:,.2f} (avg {avg_pnl_pct:+.2f}%)<br>Time: {np.datetime64(b_ms, 'ms')}"
            )

    return times, prices, hover_texts


def add_chart_traces(
    fig: Figure,
    stats: Stats,
    tf_series: list[ResampledData],
    trace_tf_map: list[int | None],
) -> None:
    start_price: float64 = stats.ohlc["close"][0]

    has_buy_long = any(to["is_long"] for to in stats.trades_open)
    has_sell_short = any(not to["is_long"] for to in stats.trades_open)
    has_close_long = any(tc["is_long"] for tc in stats.trades_close)
    has_close_short = any(not tc["is_long"] for tc in stats.trades_close)

    # Candles and Trade markers for every timeframe
    for tf_idx, tf_data in enumerate(tf_series):
        is_active: bool = tf_idx == 0
        tf_ms: int = tf_data["timeframe_ms"]

        # Candle
        fig.add_trace(  # pyright: ignore[reportUnknownMemberType]
            Candlestick(
                x=tf_data["ohlc"]["time"],
                open=tf_data["ohlc"]["open"],
                high=tf_data["ohlc"]["high"],
                low=tf_data["ohlc"]["low"],
                close=tf_data["ohlc"]["close"],
                name=f"OHLC ({tf_data['timeframe_name']})",
                increasing_line_color="#CFD8DC",
                increasing_fillcolor="#37474F",
                decreasing_line_color="#455A64",
                decreasing_fillcolor="#212121",
                showlegend=False,
                visible=is_active,
            ),
            row=2,
            col=1,
            secondary_y=False,
        )
        trace_tf_map.append(tf_idx)

        # Right Y tick in %
        fig.add_trace(  # pyright: ignore[reportUnknownMemberType]
            Scatter(
                x=tf_data["ohlc"]["time"],
                y=tf_data["rel_price_pct"],
                mode="lines",
                line={"color": "rgba(0,0,0,0)", "width": 0},
                showlegend=False,
                hoverinfo="skip",
                visible=is_active,
            ),
            row=2,
            col=1,
            secondary_y=True,
        )
        trace_tf_map.append(tf_idx)

        # Trade Markers
        if has_buy_long:
            x_bl, y_bl, h_bl = _group_open_trades(
                stats.trades_open, tf_ms, is_long=True
            )
            fig.add_trace(  # pyright: ignore[reportUnknownMemberType]
                Scatter(
                    x=x_bl,
                    y=y_bl,
                    mode="markers",
                    marker={
                        "symbol": "triangle-up",
                        "size": 10,
                        "color": "#00E676",
                        "line": {"width": 1.2, "color": "#121212"},
                    },
                    name="Long Entry",
                    legend="legend2",
                    showlegend=(tf_idx == 0),
                    hovertext=h_bl,
                    hoverinfo="text",
                    visible=is_active,
                ),
                row=2,
                col=1,
                secondary_y=False,
            )
            trace_tf_map.append(tf_idx)

        if has_sell_short:
            x_ss, y_ss, h_ss = _group_open_trades(
                stats.trades_open, tf_ms, is_long=False
            )
            fig.add_trace(  # pyright: ignore[reportUnknownMemberType]
                Scatter(
                    x=x_ss,
                    y=y_ss,
                    mode="markers",
                    marker={
                        "symbol": "triangle-down",
                        "size": 10,
                        "color": "#FF1744",
                        "line": {"width": 1.2, "color": "#121212"},
                    },
                    name="Short Entry",
                    legend="legend2",
                    showlegend=(tf_idx == 0),
                    hovertext=h_ss,
                    hoverinfo="text",
                    visible=is_active,
                ),
                row=2,
                col=1,
                secondary_y=False,
            )
            trace_tf_map.append(tf_idx)

        if has_close_long:
            x_cl, y_cl, h_cl = _group_close_trades(
                stats.trades_close, tf_ms, is_long=True
            )
            fig.add_trace(  # pyright: ignore[reportUnknownMemberType]
                Scatter(
                    x=x_cl,
                    y=y_cl,
                    mode="markers",
                    marker={
                        "symbol": "x",
                        "size": 8,
                        "color": "#00E676",
                        "line": {"width": 1.5, "color": "#121212"},
                    },
                    name="Close Long",
                    legend="legend2",
                    showlegend=(tf_idx == 0),
                    hovertext=h_cl,
                    hoverinfo="text",
                    visible=is_active,
                ),
                row=2,
                col=1,
                secondary_y=False,
            )
            trace_tf_map.append(tf_idx)

        if has_close_short:
            x_cs, y_cs, h_cs = _group_close_trades(
                stats.trades_close, tf_ms, is_long=False
            )
            fig.add_trace(  # pyright: ignore[reportUnknownMemberType]
                Scatter(
                    x=x_cs,
                    y=y_cs,
                    mode="markers",
                    marker={
                        "symbol": "x",
                        "size": 8,
                        "color": "#FF1744",
                        "line": {"width": 1.5, "color": "#121212"},
                    },
                    name="Close Short",
                    legend="legend2",
                    showlegend=(tf_idx == 0),
                    hovertext=h_cs,
                    hoverinfo="text",
                    visible=is_active,
                ),
                row=2,
                col=1,
                secondary_y=False,
            )
            trace_tf_map.append(tf_idx)

    # Base Price Line
    fig.add_trace(  # pyright: ignore[reportUnknownMemberType]
        Scatter(
            x=[stats.ohlc["time"][0], stats.ohlc["time"][-1]],
            y=[float(start_price), float(start_price)],
            mode="lines",
            line={"color": "#757575", "width": 1, "dash": "dash"},
            showlegend=False,
            hoverinfo="skip",
        ),
        row=2,
        col=1,
        secondary_y=False,
    )
    trace_tf_map.append(None)
