import numpy as np
import plotly.graph_objects as go  # pyright: ignore[reportMissingTypeStubs]
from numpy import float64
from numpy.typing import NDArray

from imprint.visualization.analyze import Stats
from imprint.visualization.analyze.resample import ResampledData


def add_equity_traces(
    fig: go.Figure,
    stats: Stats,
    tf_series: list[ResampledData],
    trace_tf_map: list[int | None],
) -> None:
    base_balance: float = stats.start_balance

    # Timeframe-dependent traces (Fills, Dynamic DD, Equity curve)
    for tf_idx, tf_data in enumerate(tf_series):
        is_active: bool = tf_idx == 0
        base_line_eq: NDArray[float64] = np.full_like(
            tf_data["eq_close"], base_balance, dtype=float64
        )

        fig.add_trace(  # pyright: ignore[reportUnknownMemberType]
            go.Scatter(
                x=tf_data["eq_times"],
                y=base_line_eq,
                mode="lines",
                line={"color": "rgba(0,0,0,0)", "width": 0},
                showlegend=False,
                hoverinfo="skip",
                visible=is_active,
            ),
            row=1,
            col=1,
            secondary_y=False,
        )
        trace_tf_map.append(tf_idx)

        fig.add_trace(  # pyright: ignore[reportUnknownMemberType]
            go.Scatter(
                x=tf_data["eq_times"],
                y=np.maximum(tf_data["eq_close"], base_balance),
                mode="lines",
                line={"color": "rgba(0,0,0,0)", "width": 0},
                fill="tonexty",
                fillcolor="rgba(0, 230, 118, 0.16)",
                showlegend=False,
                hoverinfo="skip",
                visible=is_active,
            ),
            row=1,
            col=1,
            secondary_y=False,
        )
        trace_tf_map.append(tf_idx)

        fig.add_trace(  # pyright: ignore[reportUnknownMemberType]
            go.Scatter(
                x=tf_data["eq_times"],
                y=base_line_eq,
                mode="lines",
                line={"color": "rgba(0,0,0,0)", "width": 0},
                showlegend=False,
                hoverinfo="skip",
                visible=is_active,
            ),
            row=1,
            col=1,
            secondary_y=False,
        )
        trace_tf_map.append(tf_idx)

        fig.add_trace(  # pyright: ignore[reportUnknownMemberType]
            go.Scatter(
                x=tf_data["eq_times"],
                y=np.minimum(tf_data["eq_close"], base_balance),
                mode="lines",
                line={"color": "rgba(0,0,0,0)", "width": 0},
                fill="tonexty",
                fillcolor="rgba(255, 23, 68, 0.16)",
                showlegend=False,
                hoverinfo="skip",
                visible=is_active,
            ),
            row=1,
            col=1,
            secondary_y=False,
        )
        trace_tf_map.append(tf_idx)

        # Dynamic Drawdown Line with legend
        if tf_data["dynamic_drawdowns"]:
            fig.add_trace(  # pyright: ignore[reportUnknownMemberType]
                go.Scatter(
                    x=tf_data["eq_times"],
                    y=tf_data["dynamic_drawdowns"],
                    mode="lines",
                    line={
                        "color": "rgba(255, 82, 82, 0.75)",
                        "width": 1.2,
                        "dash": "dot",
                    },
                    name="Dynamic DD",
                    yaxis="y5",
                    legend="legend",
                    hovertemplate="Dynamic DD: %{y:.2f}%<extra></extra>",
                    visible=is_active,
                )
            )
            trace_tf_map.append(tf_idx)

        # Equity Line
        fig.add_trace(  # pyright: ignore[reportUnknownMemberType]
            go.Scatter(
                x=tf_data["eq_times"],
                y=tf_data["eq_close"],
                mode="lines",
                line={"color": "#00E5FF", "width": 2.0},
                name=f"Equity ({tf_data['timeframe_name']})",
                legend="legend",
                customdata=tf_data["eq_close"] - base_balance,
                hovertemplate="Time: %{x}<br>Equity: $%{y:,.2f}<br>Profit: $%{customdata:,.2f}<extra></extra>",
                visible=is_active,
            ),
            row=1,
            col=1,
            secondary_y=False,
        )
        trace_tf_map.append(tf_idx)

        fig.add_trace(  # pyright: ignore[reportUnknownMemberType]
            go.Scatter(
                x=tf_data["eq_times"],
                y=tf_data["rel_equity_pct"],
                mode="lines",
                line={"color": "rgba(0,0,0,0)", "width": 0},
                showlegend=False,
                hoverinfo="skip",
                visible=is_active,
            ),
            row=1,
            col=1,
            secondary_y=True,
        )
        trace_tf_map.append(tf_idx)

    fig.add_trace(  # pyright: ignore[reportUnknownMemberType]
        go.Scatter(
            x=[stats.eq_times[0], stats.eq_times[-1]],
            y=[base_balance, base_balance],
            mode="lines",
            line={"color": "#9E9E9E", "width": 1, "dash": "dash"},
            showlegend=False,
            hoverinfo="skip",
        ),
        row=1,
        col=1,
        secondary_y=False,
    )
    trace_tf_map.append(None)

    if stats.static_drawdowns:
        times_close = [tc["time"] for tc in stats.trades_close]
        fig.add_trace(  # pyright: ignore[reportUnknownMemberType]
            go.Scatter(
                x=times_close,
                y=stats.static_drawdowns,
                mode="lines",
                fill="tozeroy",
                fillcolor="rgba(255, 23, 68, 0.12)",
                line={"color": "#FF1744", "width": 1},
                name="Static DD",
                legend="legend",
                yaxis="y5",
                hovertemplate="Static DD: %{y:.2f}%<extra></extra>",
            )
        )
        trace_tf_map.append(None)
