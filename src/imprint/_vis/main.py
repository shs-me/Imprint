import json
import os
from datetime import UTC, datetime

import numpy as np
import streamlit as st
from loguru import logger

from imprint._core import constant as c
from imprint._core.types import RunData
from imprint._vis.analyze.base import Stats
from imprint._vis.plot import (
    plot_equity_and_chart,
    plot_info_dashboard,
    plot_trade_distribution,
)
from imprint._vis.prepare import (
    get_headers_path,
    get_need_headers_range,
    get_ohlc,
)

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


def load_manifest() -> list[RunData]:
    if not os.path.exists(c.MANIFEST_PATH):
        logger.warning(
            f"Manifest not found at {c.MANIFEST_PATH}. Run backtest first."
        )
        st.warning("Manifest not found. Please run backtest first.")
        st.stop()

    with open(c.MANIFEST_PATH, "r", encoding="utf-8") as f:
        try:
            data: list[RunData] = json.load(f)
            return data
        except json.JSONDecodeError as err:
            logger.error(f"Error parsing manifest.json: {err}")
            st.error("Error reading manifest.json.")
            st.stop()


manifest = load_manifest()

if not manifest:
    logger.info("Manifest is empty")
    st.info("Manifest is empty. No completed backtest runs found.")
    st.stop()


# LAYER 1: Overview & Runs Table
if st.session_state.selected_run_id is None:
    st.title("📊 Backtest Overview")

    # Aggregate summary metrics
    total_runs = len(manifest)
    profitable_runs = sum(1 for item in manifest if item["net_profit"] > 0)
    win_rate = (profitable_runs / total_runs * 100) if total_runs else 0.0

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

    st.subheader("Select a Run to Inspect")

    # Table with interactive selection
    event = st.dataframe(  # pyright: ignore[reportUnknownMemberType]
        overview_rows,
        width="stretch",
        hide_index=True,
        on_select="rerun",
        selection_mode="single-row",
    )

    # Check if a row was clicked directly in the dataframe
    selected_row_indices = (
        event.selection.rows if hasattr(event, "selection") else []
    )
    if selected_row_indices:
        clicked_idx = selected_row_indices[0]
        st.session_state.selected_run_id = manifest[clicked_idx]["id"]
        st.rerun()

# LAYER 2: Detailed Run Analysis Drilldown
else:
    run_id = st.session_state.selected_run_id
    run_map = {item["id"]: item for item in manifest}

    if run_id not in run_map:
        st.session_state.selected_run_id = None
        st.rerun()

    run = run_map[run_id]

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
        try:
            equity_data = np.load(f"{c.RUNS_DIR}/equity_{run['id']}.npy")
            orders_data = np.load(f"{c.RUNS_DIR}/orders_{run['id']}.npy")
        except FileNotFoundError as err:
            logger.error(f"Failed to load run artifacts: {err}")
            st.error(f"Run data files not found: {err}")
            st.stop()

        start_date = datetime.fromisoformat(run["start_date"]).replace(
            tzinfo=UTC
        )
        end_date = datetime.fromisoformat(run["end_date"]).replace(tzinfo=UTC)

        headers_path = get_headers_path(
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
            raw_headers = np.load(headers_path)
        except FileNotFoundError as err:
            logger.error(err)
            st.error(err)
            st.stop()

        headers_range = get_need_headers_range(
            start_date=start_date, end_date=end_date, headers=raw_headers
        )
        ohlc = get_ohlc(headers=headers_range, price_mult=run["price_mult"])

        stats = Stats(
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

    tab1, tab2, tab3 = st.tabs(
        [
            "📋 Performance KPI Dashboard",
            "🎯 Trade Distribution (MAE / MFE)",
            "📈 Equity & Interactive Chart",
        ]
    )

    with tab1:
        st.plotly_chart(plot_info_dashboard(stats), width="stretch")  # pyright: ignore[reportUnknownMemberType]

    with tab2:
        st.plotly_chart(plot_trade_distribution(stats), width="stretch")  # pyright: ignore[reportUnknownMemberType]

    with tab3:
        st.plotly_chart(plot_equity_and_chart(stats), width="stretch")  # pyright: ignore[reportUnknownMemberType]
