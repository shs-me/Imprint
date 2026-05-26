# GridCore Engine: Technical Reference & Architecture Manual

This documentation provides a technical reference for **GridCore**, a high-performance, low-latency multiprocessing trading and backtesting engine. The architecture relies on Python's `multiprocessing.shared_memory` to eliminate Inter-Process Communication (IPC) overhead, utilizing double-buffered memory arenas, Numba-compiled execution paths, and structured status code signaling.

---

## 1. System Architecture & Concurrency Model

GridCore separates tasks into independent, dedicated OS processes synchronized via standard multiprocessing `Event` and `Semaphore` primitives. Data exchange is strictly off-heap, executing directly inside shared memory slices.

```
       +---------------------------------------------+
       |             WssSimAgent / WssAgent          |  (Network / Sim)
       +----------------------+----------------------+
                              | writes bytes
                              v
                [ ConfigurationRingRawBuf ]             (Shared Memory Ring)
                              |
                              | parsing_event.wait()
                              v
       +----------------------+----------------------+
       |                  ParserAgent                |  (Parsing & Aggregation)
       +----------------------+----------------------+
                              | writes footprint & headers
                              v
                [ ConfigurationFootprint ]              (Shared Memory Footprint)
                              |
                              | logic_event.wait()
                              v
       +----------------------+----------------------+
       |                  LogicAgent                 |  (Strategy & Pattern Search)
       +----------------------+----------------------+
                              | writes signals
                              v
                  [ ConfigurationStrategy ]             (Shared Memory Signals)
                              |
                              | execution_event.wait()
                              v
       +----------------------+----------------------+
       |                 ExecutionAgent              |  (Order Matcher / Execution)
       +---------------------------------------------+
```

---

## 2. Shared Memory Map (SHM Slices)

Memory slices are mapped via `configurations.py` using absolute byte offsets. All numerical data is encoded using C-types: `UBYTE` (1 byte), `INT64` (8 bytes), and `FLOAT64` (8 bytes).

### 2.1 `ConfigurationRingRawBuf`
An $N$-cell circular buffer designed for lock-free single-writer, single-reader raw byte transfers between the streaming agent and the parser.

*   **`ReaderCellCounter`** `[Offset: 0, Size: 8 bytes, Type: INT64]`: Points to the cell index currently being processed by the reader.
*   **`WriterCellCounter`** `[Offset: 8, Size: 8 bytes, Type: INT64]`: Points to the cell index being written by the streaming agent.
*   **`dataHeader`** `[Offset: 16, Size: N bytes, Type: UBYTE]`: Array containing the exact byte-length of the payload inside each cell.
*   **`data`** `[Offset: 16 + N, Size: N * 256 bytes, Type: BYTES]`: Raw data cells storing serialized JSON ticks.

### 2.2 `ConfigurationFootprint`
Maintains the real-time order flow matrix (Footprint), OHLC Bar Headers, and coordination flags.

*   **`footprint`** `[Size: fpLines * fpPanelCols * 8 bytes, Type: INT64]`: 2D Matrix representing volumes traded per price cluster (Bids, Asks, Volume Profile, Delta Profile).
*   **`headers`** `[Size: bar_count * 17 * 8 bytes, Type: INT64]`: Array of structured OHLC indicators and volume analytics defined by `BarHeaders`.
*   **`space`** `[Size: 2 * 4 * 8 bytes, Type: INT64]`: Active coordinate bounding box `[IDYmin, IDXmin, IDYmax, IDXmax]` for double-buffered reading.
*   **`space_read`** `[Size: 1 byte, Type: UBYTE]`: Coordination flag. Signaled when the logic process finishes reading the current active space, indicating the matching engine can safely consume the data.

### 2.3 `ConfigurationMetrics`
Holds execution state, precision scalers, and double-buffered tick-matching data.

*   **`tick_size`, `lot_size`, `pricePrecision`, `qtyPrecision`** `[Size: 4 * 8 bytes, Type: INT64]`: Precision configuration parameters parsed from the exchange exchange rules.
*   **`dfm_1` / `dfm_2`** `[Size: dfmLines * 3 * 8 bytes, Type: INT64]`: Double-buffered arrays storing `[nPrice, startTimestamp, endTimestamp]` used by the matching engine to replay orders.
*   **`dfm_1_row_id` / `dfm_2_row_id`** `[Size: 8 bytes, Type: INT64]`: Pointer tracking active write rows in the respective DFM buffer.

---

## 3. Core Class Reference

### 3.1 `FPconverter` (Namespace: `core.engine.agents_utils.utils`)
Manages conversion scales and translation between floating-point exchange coordinates and high-precision integer matrix coordinates.

```python
class FPconverter:
    def __init__(self, footprint: NDArray[int64], headers: NDArray[int64], 
                 trade_param: memoryview, cfgFP: ConfigurationFootprint)
```

#### Key Methods

*   `to_idy(nPrice: int) -> int | None`
    Translates an integer-scaled price to the Y-axis index of the footprint matrix relative to the base session price.
*   `to_idx(timestamp: int, is_sell: bool) -> int | None`
    Translates an epoch millisecond timestamp and trade direction into the X-axis column index of the footprint matrix.
*   `to_nPrice(value: float) -> int`
    Scales a float exchange price to a high-precision integer (typically $10^{20}$).
*   `to_nQty(qty: float) -> int`
    Scales a float volume to a high-precision integer.

---

### 3.2 `TradeConverter` (Namespace: `core.engine.agents_utils.utils`)
Mathematical kernel managing high-precision account accounting, margin locking, and PnL conversions.

```python
class TradeConverter:
    def __init__(self, trade_param: memoryview, cfgStrategy: ConfigurationStrategy)
```

#### Properties

*   `nBalance` `[Type: int]`: High-precision account balance. Raises `RuntimeError` (triggering an emergency exit) if balance drops below the maximum loss threshold defined by `MaxLossBalance`.
*   `availableNbalance` `[Type: int]`: Calculated as `nBalance - lockedNbalance`. Represents free margin.
*   `nominalEntryNqty` `[Type: int]`: Baseline position size based on current available balance and `EntryQty` scaling.

#### Key Methods

*   `to_nPnl(closeNprice: int, nQty: int, is_long: bool) -> int`
    Calculates integer-based trade PnL based on position direction and entry price:
    $$\text{PnL} = (\text{closeNprice} - \text{entryNprice}) \times \text{nQty} \times \text{Direction}$$
*   `to_nMargin(nPrice: int, nQty: int) -> int`
    Calculates the margin required to open a position based on leverage:
    $$\text{Margin} = \frac{\text{nQty} \times \text{nPrice}}{\text{Scale} \times \text{Leverage}}$$

---

### 3.3 `FootprintWriter` (Namespace: `core.engine.agents_utils.parsing.footprint_writer`)
Compiles incoming raw ticks into structured bar metrics, calculating VWAP, Bollinger Bands, Volume Area, and POC.

```python
class FootprintWriter:
    def __init__(self, manager: AgentManager)
```

#### Key Methods

*   `update(price: float, qty: float, timestamp: int, is_sell: bool) -> bool`
    Updates active footprint matrix cell volumes, updates bar OHLC bounds, and recalculates the running session VWAP. Passes data to double-buffered storage when a boundary is crossed.
*   `update_dfm(nPrice: int, timestamp: int) -> bool`
    Compresses subsequent trades occurring at identical prices into a single matching row inside the active DFM buffer.

---

### 3.4 `FootprintReader` (Namespace: `core.engine.agents_utils.logic.footprint_reader`)
Abstract base class for reading thecompiled footprint state and generating signals.

```python
class FootprintReader(ABC):
    def __init__(self, manager: AgentManager, execution_event: Event)
```

#### Key Methods

*   `update_states() -> None`
    Reads the active spatial coordinate slice from shared memory and updates cluster structures, bar-indicators, and value areas.
*   `send_signal(nPrice: int, time_ms: int, is_long: bool, is_buy: bool, is_market: bool, pass_lag: bool) -> None`
    Serializes a trade signal directly into the strategy shared memory block (`executeBuf`) and triggers `execution_event`.

---

### 3.5 `MatchingEngine` (Namespace: `core.engine.agents_utils.execution.matching_engine`)
Replays historical price updates stored in the DFM buffer to determine order fills, Take-Profits, and Stop-Loss triggers.

```python
class MatchingEngine:
    def __init__(self, manager: AgentManager, con: TradeConverter, tm: TradeManager)
```

#### Key Methods

*   `prepare_dfm(timestamp: int | None) -> None`
    Processes all un-matched rows from the active DFM buffer up to the current timestamp. Evaluates order state machines sequentially.
*   `check_open_order(aoRow: int, _nPrice: int, endTimestamp: int) -> bool`
    Evaluates if an open order was filled based on DFM price boundaries. If filled, sets up the corresponding TP (Limit) and SL (Market Trigger) active child orders.

---

### 3.6 `TradeManager` (Namespace: `core.engine.agents_utils.execution.trade_manager`)
Manages the active order book matrices and persists trade records to disk.

```python
class TradeManager:
    def __init__(self, converter: TradeConverter)
```

#### Key Methods

*   `updatePosition(nPrice: int, nQty: int, nCommission: int, is_open: bool, is_long: bool) -> None`
    Modifies net exposure, recalculates current average entry price using high-precision integer math, handles margin releases, and posts PnL adjustments.
*   `set_active_order(nPrice: int, nQty: int, timestamp: int, orderParam: int, ...)`
    Registers an order inside the structured 3D numpy memory array `active_orders` (Dimensions: `[Order Type, Row, Column]`).

---

## 4. Execution Pipeline & Event Synchronization

To maintain strict execution ordering across parallel processes during simulation, GridCore uses a deterministic handoff sequence:

```
[Sim / Network] -> Writes Raw Bytes -> Triggers parsing_event
[Parser]        -> Compiles raw bytes -> Recalculates metrics -> Triggers logic_event
[Logic]         -> Runs pattern check -> Triggers execution_event -> Blocks on space_read
[Execution]     -> Replays DFM matches -> Clears space_read -> Unblocks Logic
```

This cycle ensures that the strategy logic never processes a bar until the parser has cleanly finished writing it, and the parsing process never overwrites a memory segment until the matching engine has fully replayed the price action.
