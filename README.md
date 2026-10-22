<div align="center">

# Imprint

**Multiprocess engine for algorithmic footprint (order-flow) strategies: backtesting & live execution**

[![Python 3.13](https://img.shields.io/badge/python-3.13-blue.svg)](https://www.python.org/downloads/)
[![CI](https://github.com/shs-me/Imprint/actions/workflows/ci.yml/badge.svg)](https://github.com/shs-me/Imprint/actions/workflows/ci.yml)
[![Basedpyright: strict](https://img.shields.io/badge/basedpyright-strict-blueviolet)](https://github.com/DetachHead/basedpyright)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![License: MPL 2.0](https://img.shields.io/badge/License-MPL_2.0-brightgreen.svg)](https://opensource.org/licenses/MPL-2.0)
[![Status: alpha](https://img.shields.io/badge/status-0.2.0--alpha-orange.svg)](#status--known-limitations)

</div>

---

## What is Imprint?

**Imprint** is a framework built specifically for traders and developers who trade market microstructure and footprint charts (cluster volume, delta profiles, auction imbalances).

Its purpose is straightforward:
1. **Codify** manual footprint and volume cluster patterns into algorithmic rules.
2. **Backtest & Optimize** strategies across historical tick-level trade batches.
3. **Automate Live Execution** on crypto futures using the exact same strategy code without rewriting logic.

---

## Technical Design & Decisions

### 1. Multiprocessing & Shared Memory
Processing tick-level trades, recalculating cluster matrices, and routing orders concurrently in a single Python thread creates latency and missed events due to the GIL.

Imprint runs **three dedicated OS processes** linked via pre-allocated shared memory ring buffers (`multiprocessing.shared_memory`):
* **Streaming**: Ingests historical aggregated trade files (`.npz`) or connects to exchange WebSockets.
* **Engine**: Builds footprint clusters, calculates indicators (VWAP, CVD, POC, Value Area), and runs the strategy loop.
* **Executing**: Evaluates orders against a tick-by-tick matching simulator (`exchange_sim`) in backtest or routes them via exchange WebSocket APIs in live.

### 2. Strictly Typed `int64` Architecture
The performance-critical cluster calculations, matching engine, and indicators are compiled with **Numba** and stored in **NumPy** arrays. 

Because Numba and NumPy do not support arbitrary-precision integers or `int128`, everything inside the engine (prices, quantities, margins, commissions, balances) is standardized to **scaled fixed-point `int64` integers**. This keeps memory layouts uniform, eliminates float representation nuances, and allows JIT-compiled kernels to run with zero allocations.

### 3. Bounding Box (BBOX) Dirty Tracking
Instead of scanning the entire price-time grid on every trade, the engine tracks a dirty bounding box (min/max price and column modified by incoming trades). Indicator updates, volume profile calculations, and strategy callbacks only evaluate cells within the active BBOX.

---

## Installation

Requires **Python 3.13** (`>=3.13,<3.14`).

```bash
git clone https://github.com/shs-me/Imprint.git
cd Imprint

python -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate

pip install -e ".[all]"        # Installs numba, msgspec, streamlit, plotly, pytest, ruff
```

---

## Workflow & Examples

Strategy development is decoupled into two classes:
* **`StrategyEngine`**: Receives footprint bars (`self.fp`), cluster states, and bar events (`on_bar_update`, `on_bar_close`). Emits trading signals.
* **`ExecutionEngine`**: Handles order routing, position state tracking, bracket orders (TP/SL), and fills (`on_signal`, `on_filled_order`, `on_canceled_order`).

### Minimal Backtest Setup

```python
import imprint
from imprint import pct, tf

from example.algorithm import IntraDay
from example.execution import HedgeExecution

# Fluent builder for backtesting configurations
bt = imprint.backtest(
    symbols=["DASHUSDT"],
    tick_size=["0.01"],
    lot_size=["0.001"],
    start_date=["2026-01-01"],
    end_date=["2026-01-07"],
    with_execution=True,
    pass_debug_logs=False,
)

bt.account(
    leverage=[50],
    balance=[5000.0],
    min_order_size=[5.0],
    taker_commission=[pct(0.05)],
    maker_commission=[pct(0.02)],
    slippage=[pct(0.05)],
    latency_ms=[100],
)

bt.footprint(timeframe=[tf.M5], step_tick=[5], state=[True], ctrade=[True])
bt.risk_management(entry_qty=[pct(0.5)], tp_dev=[pct(2.0)], sl_dev=[pct(1.5)])
bt.strategy(algorithm=[IntraDay], execution=[HedgeExecution])

bt.build()

bt.engine.run_core()  # Runs the multiprocessing pipeline and saves .npy dumps
bt.engine.run_vis()   # Launches the Streamlit performance dashboard
```

> 💡 **Full Working Examples**: See the [`example/`](./example) directory for:
> * [`example/algorithm.py`](./example/algorithm.py) — Working footprint strategy inspecting trapped market orders and POC levels.
> * [`example/execution.py`](./example/execution.py) — Execution router managing bracket TP/SL orders and cancellations.
> * [`example/main.py`](./example/main.py) — Runnable script for both Backtest and Live modes.
> * Protocol decoders & encoders for Binance and Bybit futures.

---

## Visualization

Backtests save run artifacts (`equity_*.npy`, `orders_*.npy`, `footprint_headers/`) and log run metadata to `data/runs/manifest.json`.

You can inspect the results using the built-in Streamlit app:

```bash
streamlit run src/imprint/_vis/main.py
```

The visualizer provides:
* **Run Manifest Table**: Compare batch runs, net profit, trade counts, and configuration parameters.
* **Performance Metrics**: Sharpe, Sortino, Calmar, Van Tharp SQN, Kelly Criterion, and drawdown stats.
* **Trade Distribution**: Visualizes realized PnL against Maximum Adverse Excursion (MAE) and Maximum Favorable Excursion (MFE).
* **Synchronized Chart**: Resampled candlesticks aligned with trade executions and dynamic equity/drawdown curves.

---

## Status & Known Limitations

**Version: `0.2.0-alpha`**. The core architecture is functional, but it is experimental software under active development:

* **Single-Instrument per Pipeline**: The footprint matrix is structured around a single symbol per running process pipeline. Multi-symbol testing runs sequentially across configuration batches.
* **Aggregated Trades Feed**: Built for tick-level trade streams (`aggTrades`). It does not reconstruct Level 2 (L2) full order book depth.
* **Shared Memory Cleanup**: Clean termination relies on proper worker shutdowns. Forcibly terminating processes (`kill -9`) can orphan segments in `/dev/shm`.
* **Adapters**: Binance Futures adapters are tested; Bybit adapters in `example/bybit/` are currently reference stubs.

---

## Disclaimer

This software is for research and educational purposes only. Always test thoroughly in simulation before connecting real capital to any exchange API.

## License

Mozilla Public License 2.0 ([MPL-2.0](LICENSE)).
