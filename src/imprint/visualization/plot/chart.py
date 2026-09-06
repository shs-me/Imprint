import plotly.graph_objects as go  # pyright: ignore[reportMissingTypeStubs]
from numpy import float64

from imprint.visualization.analyze import Stats
from imprint.visualization.analyze.resample import ResampledData
from imprint.visualization.settings import CloseTrades, OpenTrades


def add_chart_traces(
    fig: go.Figure,
    stats: Stats,
    tf_series: list[ResampledData],
    trace_tf_map: list[int | None],
) -> None:
    start_price: float64 = stats.ohlc["close"][0]

    # Candles for every Timeframe
    for tf_idx, tf_data in enumerate(tf_series):
        is_active: bool = tf_idx == 0

        # Candle
        fig.add_trace(  # pyright: ignore[reportUnknownMemberType]
            go.Candlestick(
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
            go.Scatter(
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

    # Base Price Line
    fig.add_trace(  # pyright: ignore[reportUnknownMemberType]
        go.Scatter(
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

    # Trade Markers with legend
    buy_long: list[OpenTrades] = [
        to for to in stats.trades_open if to["is_long"]
    ]
    if buy_long:
        fig.add_trace(  # pyright: ignore[reportUnknownMemberType]
            go.Scatter(
                x=[to["time"] for to in buy_long],
                y=[to["price"] for to in buy_long],
                mode="markers",
                marker={
                    "symbol": "triangle-up",
                    "size": 10,
                    "color": "#00E676",
                    "line": {"width": 1.2, "color": "#121212"},
                },
                name="Long Entry",
                legend="legend2",
                hovertemplate="Entry Long: $%{y:,.2f}<br>Time: %{x}<extra></extra>",
            ),
            row=2,
            col=1,
            secondary_y=False,
        )
        trace_tf_map.append(None)

    sell_short: list[OpenTrades] = [
        to for to in stats.trades_open if not to["is_long"]
    ]
    if sell_short:
        fig.add_trace(  # pyright: ignore[reportUnknownMemberType]
            go.Scatter(
                x=[to["time"] for to in sell_short],
                y=[to["price"] for to in sell_short],
                mode="markers",
                marker={
                    "symbol": "triangle-down",
                    "size": 10,
                    "color": "#FF1744",
                    "line": {"width": 1.2, "color": "#121212"},
                },
                name="Short Entry",
                legend="legend2",
                hovertemplate="Entry Short: $%{y:,.2f}<br>Time: %{x}<extra></extra>",
            ),
            row=2,
            col=1,
            secondary_y=False,
        )
        trace_tf_map.append(None)

    close_long: list[CloseTrades] = [
        tc for tc in stats.trades_close if tc["is_long"]
    ]
    if close_long:
        fig.add_trace(  # pyright: ignore[reportUnknownMemberType]
            go.Scatter(
                x=[tc["time"] for tc in close_long],
                y=[tc["price"] for tc in close_long],
                mode="markers",
                marker={
                    "symbol": "x",
                    "size": 8,
                    "color": "#00E676",
                    "line": {"width": 1.5, "color": "#121212"},
                },
                name="Close Long",
                legend="legend2",
                customdata=[[tc["pnl"], tc["pnl_pct"]] for tc in close_long],
                hovertemplate="Close Long: $%{y:,.2f}<br>PnL: $%{customdata[0]:,.2f} (%{customdata[1]:+.2f}%)<extra></extra>",
            ),
            row=2,
            col=1,
            secondary_y=False,
        )
        trace_tf_map.append(None)

    close_short: list[CloseTrades] = [
        tc for tc in stats.trades_close if not tc["is_long"]
    ]
    if close_short:
        fig.add_trace(  # pyright: ignore[reportUnknownMemberType]
            go.Scatter(
                x=[tc["time"] for tc in close_short],
                y=[tc["price"] for tc in close_short],
                mode="markers",
                marker={
                    "symbol": "x",
                    "size": 8,
                    "color": "#FF1744",
                    "line": {"width": 1.5, "color": "#121212"},
                },
                name="Close Short",
                legend="legend2",
                customdata=[[tc["pnl"], tc["pnl_pct"]] for tc in close_short],
                hovertemplate="Close Short: $%{y:,.2f}<br>PnL: $%{customdata[0]:,.2f} (%{customdata[1]:+.2f}%)<extra></extra>",
            ),
            row=2,
            col=1,
            secondary_y=False,
        )
        trace_tf_map.append(None)
