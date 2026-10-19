import json
import os

import numpy as np
import streamlit as st
from loguru import logger
from plotly.graph_objects import (  # pyright: ignore[reportMissingTypeStubs]
    Figure,
)
from streamlit.elements.arrow import DataframeState

import imprint._core.constant as c
from imprint._core.types import RunData
from imprint._vis.analyze.base import Stats

st.set_page_config(
    layout="wide", page_title="Imprint Backtest Visualizer", page_icon="📈"
)

st.markdown(
    """
<style>
    .reportview-container { background: #121212; }
    div[data-testid="stMetricValue"] { font-size: 22px; }
</style>
""",
    unsafe_allow_html=True,
)

# Initialize navigation state
if "selected_run_id" not in st.session_state:
    st.session_state.selected_run_id = None

# Initialize logging
if "logger_initialized" not in st.session_state:
    import imprint._boot.logger  # noqa: F401 # pyright: ignore[reportUnusedImport]

    st.session_state.logger_initialized = True

but1, but2 = st.columns(2, gap=None)

clear_cache: bool = but1.button(label="Clear Cache")
if clear_cache:
    with st.spinner("Clearing cache data..."):
        st.cache_data.clear()


@st.cache_data
def load_manifest() -> list[RunData]:
    if not os.path.exists(c.RUNS_MANIFEST_PATH):
        logger.warning(
            f"Manifest not found at {c.RUNS_MANIFEST_PATH}. Run backtest first."
        )
        st.warning("Manifest not found. Please run backtest first.")
        st.stop()

    with open(c.RUNS_MANIFEST_PATH, "r", encoding="utf-8") as f:
        try:
            data: list[RunData] = json.load(f)
            return data
        except json.JSONDecodeError as err:
            logger.error(f"Error parsing manifest.json: {err}")
            st.error("Error reading manifest.json.")
            st.stop()


manifest: list[RunData] = load_manifest()

if not manifest:
    logger.info("Manifest is empty")
    st.info("Manifest is empty. No completed backtest runs found.")
    st.stop()


@st.cache_data
def compute_analytics(run: RunData) -> Stats:
    from datetime import UTC, datetime

    from imprint._core.utils.base import (
        EquityHistoryArray,
        FPHeadersArray,
        OrdersHistoryArray,
    )
    from imprint._vis.prepare import (
        get_headers_path,
        get_need_headers_range,
        get_ohlc,
    )
    from imprint._vis.settings import OHLC

    try:
        equity_data: EquityHistoryArray = np.load(
            f"{c.RUNS_DIR}/equity_{run['id']}.npy"
        )
        orders_data: OrdersHistoryArray = np.load(
            f"{c.RUNS_DIR}/orders_{run['id']}.npy"
        )
    except FileNotFoundError as err:
        logger.error(f"Failed to load run artifacts: {err}")
        st.error(f"Run data files not found: {err}")
        st.stop()

    start_date: datetime = datetime.fromisoformat(run["start_date"]).replace(
        tzinfo=UTC
    )
    end_date: datetime = datetime.fromisoformat(run["end_date"]).replace(
        tzinfo=UTC
    )

    headers_path: str | None = get_headers_path(
        symbol=run["symbol"],
        timeframe=run["timeframe_name"],
        start_date=start_date,
        end_date=end_date,
    )
    if headers_path is None:
        st.error(
            f"Footprint headers not found for {run['symbol']} ({run['timeframe_name']}) "
            + f"between {start_date.date()} and {end_date.date()}."
        )
        st.stop()

    try:
        raw_headers: FPHeadersArray = np.load(headers_path)
    except FileNotFoundError as err:
        logger.error(err)
        st.error(err)
        st.stop()

    headers_range: FPHeadersArray = get_need_headers_range(
        start_date=start_date, end_date=end_date, headers=raw_headers
    )
    ohlc: OHLC = get_ohlc(headers=headers_range, price_mult=run["price_mult"])
    return Stats(
        symbol=run["symbol"],
        start_date=run["start_date"],
        end_date=run["end_date"],
        start_balance=run["start_balance"],
        leverage=run["leverage"],
        timeframe=run["timeframe"],
        price_mult=run["price_mult"],
        qty_mult=run["qty_mult"],
        scale_mult=run["scale_mult"],
        equity=equity_data,
        orders=orders_data,
        ohlc=ohlc,
    )


@st.cache_data
def plotly_charts(stats: Stats) -> tuple[Figure, Figure, Figure]:
    from imprint._vis.plot import (
        plot_equity_and_chart,
        plot_info_dashboard,
        plot_trade_distribution,
    )

    return (
        plot_info_dashboard(stats),
        plot_trade_distribution(stats),
        plot_equity_and_chart(stats),
    )


def save_plots_as_image() -> None:
    import plotly.io as pio  # pyright: ignore[reportMissingTypeStubs]

    logger.info(f"{pio.defaults.default_height}{pio.defaults.default_width}")
    os.makedirs(c.RUNS_PLOTS_PATH, exist_ok=True)
    figs: list[Figure] = []
    paths: list[str] = []
    for run in manifest:
        stats: Stats = compute_analytics(run)
        info_fig, trade_fig, chart_fig = plotly_charts(stats)
        figs.append(info_fig)
        paths.append(f"{c.RUNS_PLOTS_PATH}/info_{run['id']}.png")
        figs.append(trade_fig)
        paths.append(f"{c.RUNS_PLOTS_PATH}/trade_{run['id']}.png")
        figs.append(chart_fig)
        paths.append(f"{c.RUNS_PLOTS_PATH}/chart_{run['id']}.png")

    pio._kaleido.write_images(  # pyright: ignore[reportUnknownMemberType]
        fig=figs,
        file=paths,  # pyright: ignore[reportArgumentType]
        width=1400,  # pyright: ignore[reportArgumentType]
        height=720,  # pyright: ignore[reportArgumentType]
    )


save_plots: bool = but2.button(label="Save Charts")
if save_plots:
    with st.spinner("Convert figures to images..."):
        save_plots_as_image()


@st.cache_data
def overview_table_rows() -> list[dict[str, str | int | float]]:
    overview_rows: list[dict[str, str | int | float]] = []
    for item in manifest:
        overview_rows.append(
            {
                "Run ID": item["id"],
                "Symbol": item["symbol"],
                "Timeframe": item["timeframe_name"],
                "Date Range": f"{item['start_date']} → {item['end_date']}",
                "Start Balance ($)": f"${item['start_balance']:,.2f}",
                "End Balance ($)": f"${item['end_balance']:,.2f}",
                "Net Profit ($)": item["net_profit"],
                "Count Trades": item["count_trade_close"],
            }
        )
    return overview_rows


# LAYER 1: Overview & Runs Table
if st.session_state.selected_run_id is None:
    st.title("📊 Backtest Overview")

    # Aggregate summary metrics
    total_runs: int = len(manifest)
    profitable_runs: int = sum(1 for item in manifest if item["net_profit"] > 0)
    win_rate: float = (
        (profitable_runs / total_runs * 100) if total_runs else 0.0
    )

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Total Runs", f"{total_runs}")
    m3.metric(
        "Profitable Runs", f"{profitable_runs} / {total_runs} ({win_rate:.1f}%)"
    )
    best_run = max(manifest, key=lambda x: x["net_profit"])
    m4.metric(
        "Best Run (PnL)", f"${best_run['net_profit']:,.2f} (#{best_run['id']})"
    )

    st.divider()
    st.subheader("Select a Run to Inspect")

    # Table with interactive selection
    event: DataframeState = st.dataframe(  # pyright: ignore[reportUnknownMemberType]
        overview_table_rows(),
        width="stretch",
        hide_index=True,
        on_select="rerun",
        selection_mode="single-row",
    )

    # Check if a row was clicked directly in the dataframe
    selected_row_indices: list[int] = (
        event.selection.rows if hasattr(event, "selection") else []
    )
    if selected_row_indices:
        clicked_idx: int = selected_row_indices[0]
        st.session_state.selected_run_id = manifest[clicked_idx]["id"]
        st.rerun()

# LAYER 2: Detailed Run Analysis Drilldown
else:
    run_id: int = st.session_state.selected_run_id
    run: None | RunData = None
    for run_ in manifest:
        if run_id == run_["id"]:
            run = run_

    if run is None:
        st.session_state.selected_run_id = None
        st.rerun()

    # Top header with back button
    col_back, col_title = st.columns([1, 6])
    with col_back:
        if st.button("⬅️ Back to Overview", width="stretch"):
            st.session_state.selected_run_id = None
            st.rerun()

    with col_title:
        pnl_sign = "+" if run["net_profit"] >= 0 else ""
        st.subheader(
            f"Run #{run['id']} | {run['symbol']} ({run['timeframe_name']}) | "
            + f"PnL: {pnl_sign}${run['net_profit']:,.2f}"
        )

    st.caption(
        f"Period: {run['start_date']} → {run['end_date']} | "
        + f"Leverage: {run['leverage']}x | Trades: {run['count_trade_close']}"
    )

    with st.spinner("Loading execution history and computing analytics..."):
        stats = compute_analytics(run)

    tab1, tab2, tab3 = st.tabs(
        [
            "📋 Performance KPI Dashboard",
            "🎯 Trade Distribution (MAE / MFE)",
            "📈 Equity & Interactive Chart",
        ]
    )
    fig1, fig2, fig3 = plotly_charts(stats)
    with tab1:
        st.plotly_chart(fig1, width="stretch")  # pyright: ignore[reportUnknownMemberType]

    with tab2:
        st.plotly_chart(fig2, width="stretch")  # pyright: ignore[reportUnknownMemberType]

    with tab3:
        st.plotly_chart(fig3, width="stretch")  # pyright: ignore[reportUnknownMemberType]
