from typing import Any

from plotly.graph_objects import (  # pyright: ignore[reportMissingTypeStubs]
    Figure,
)

DARK_LAYOUT: dict[str, Any] = {
    "paper_bgcolor": "#121212",
    "plot_bgcolor": "#161616",
    "font": {
        "family": "'Courier New', Consolas, monospace",
        "color": "#90A4AE",
        "size": 11,
    },
    "margin": {"l": 55, "r": 55, "t": 45, "b": 40},
    "hovermode": "x unified",
    "hoverlabel": {
        "bgcolor": "#1E1E1E",
        "font_size": 11,
        "font_family": "'Courier New', Consolas, monospace",
        "bordercolor": "#37474F",
    },
}


def get_usd(val: float) -> str:
    return "+$" if val >= 0 else "-$"


def apply_dark_theme(fig: Figure, title: str) -> Figure:
    fig.update_layout(  # pyright: ignore[reportUnknownMemberType]
        **DARK_LAYOUT,
        title={
            "text": f"<b>{title}</b>",
            "font": {
                "size": 13,
                "color": "#ECEFF1",
                "family": "'Courier New', Consolas, monospace",
            },
            "x": 0.5,
            "xanchor": "center",
            "y": 0.96,
        },
        legend={
            "bgcolor": "rgba(18, 18, 18, 0.85)",
            "bordercolor": "#37474F",
            "borderwidth": 1,
            "font": {
                "size": 10,
                "family": "'Courier New', Consolas, monospace",
            },
        },
    )
    fig.update_xaxes(  # pyright: ignore[reportUnknownMemberType]
        gridcolor="#212121",
        zerolinecolor="#37474F",
        linecolor="#616161",
        tickcolor="#616161",
        linewidth=1.5,
        showline=True,
        mirror=True,
    )
    fig.update_yaxes(  # pyright: ignore[reportUnknownMemberType]
        gridcolor="#212121",
        zerolinecolor="#37474F",
        linecolor="#616161",
        tickcolor="#616161",
        linewidth=1.5,
        showline=True,
        mirror=True,
    )
    return fig


def empty_figure(text: str = "No Trades To Display") -> Figure:
    fig = Figure()
    fig.add_annotation(  # pyright: ignore[reportUnknownMemberType]
        text=text,
        xref="paper",
        yref="paper",
        x=0.5,
        y=0.5,
        showarrow=False,
        font={"size": 14, "color": "#757575", "family": "monospace"},
    )
    fig.update_layout(**DARK_LAYOUT)  # pyright: ignore[reportUnknownMemberType]
    fig.update_xaxes(showgrid=False, showticklabels=False)  # pyright: ignore[reportUnknownMemberType]
    fig.update_yaxes(showgrid=False, showticklabels=False)  # pyright: ignore[reportUnknownMemberType]
    return fig
