"""IPC performance benchmark comparing Imprint MarketDataStream (SHM RingBuf)

against standard Python IPC alternatives (Pipe, Queue).
"""

import multiprocessing as mp
import time
from multiprocessing import Event, Process
from multiprocessing.connection import Connection
from multiprocessing.queues import Queue
from multiprocessing.shared_memory import SharedMemory
from multiprocessing.synchronize import Event as EventT
from typing import cast

from imprint._core.ipc.memory_layouts import MarketDataStream, RingBuf


# --- 1. Imprint MarketDataStream (Shared Memory Ring Buffer) ---
def _shm_consumer(
    shm_name: str, n_ticks: int, ready_ev: EventT, done_ev: EventT
) -> None:
    """Consume ticks from the pre-allocated shared memory ring buffer."""
    shm: SharedMemory = SharedMemory(name=shm_name)
    buf: memoryview = cast(memoryview, shm.buf)

    mds: MarketDataStream = MarketDataStream(count_reader=1)
    mds.bind_memory(buf)
    mds.post_init_rings()

    def run(ring: RingBuf) -> None:
        ready_ev.set()

        wid_buf, rid_buf = ring.wid_buf, ring.rid_buf
        count: int = 0
        while count < n_ticks:
            if wid_buf[0] != rid_buf[0]:
                _: memoryview = ring.get_data(reader=0)
                count += 1

        done_ev.set()

    run(mds.ring_buf)
    del mds
    buf.release()
    shm.close()


def benchmark_shm_ringbuf(n_ticks: int) -> float:
    """Run producer-consumer throughput benchmark using Imprint MarketDataStream."""
    mds_producer: MarketDataStream = MarketDataStream(count_reader=1)
    shm: SharedMemory = SharedMemory(create=True, size=mds_producer.size)
    buf: memoryview = cast(memoryview, shm.buf)

    mds_producer.bind_memory(buf)
    mds_producer.post_init_rings()

    ready_ev: EventT = Event()
    done_ev: EventT = Event()

    proc: Process = Process(
        target=_shm_consumer,
        args=(shm.name, n_ticks, ready_ev, done_ev),
        daemon=True,
    )
    proc.start()
    ready_ev.wait()

    ring: RingBuf = mds_producer.ring_buf

    t0: int = time.perf_counter_ns()
    for i in range(n_ticks):
        while ring.lag_not_is_safe():
            pass

        mds_producer.set_data_in_backtest(
            nPrice=50_000_00 + (i % 100),
            nQty=1_000,
            timestamp=1_700_000_000 + i,
            is_sell=i % 2,
        )

    done_ev.wait()
    t1: int = time.perf_counter_ns()
    proc.join()

    del ring, mds_producer
    buf.release()
    shm.close()
    shm.unlink()

    return (t1 - t0) / 1e9


# --- 2. multiprocessing.Pipe (Kernel socketpair + pickle) ---
def _pipe_consumer(
    conn: Connection, n_ticks: int, ready_ev: EventT, done_ev: EventT
) -> None:
    """Consume pickled tuples from multiprocessing.Pipe."""
    ready_ev.set()
    count: int = 0
    while count < n_ticks:
        _ = conn.recv()
        count += 1
    done_ev.set()
    conn.close()


def benchmark_pipe(n_ticks: int) -> float:
    """Run producer-consumer throughput benchmark using multiprocessing.Pipe."""
    recv_conn, send_conn = mp.Pipe(duplex=False)
    ready_ev: EventT = Event()
    done_ev: EventT = Event()

    proc: Process = Process(
        target=_pipe_consumer,
        args=(recv_conn, n_ticks, ready_ev, done_ev),
        daemon=True,
    )
    proc.start()
    ready_ev.wait()

    tick = (50_000_00, 1_000, 1_700_000_000, 1)

    t0: int = time.perf_counter_ns()
    for _ in range(n_ticks):
        send_conn.send(tick)

    done_ev.wait()
    t1: int = time.perf_counter_ns()
    proc.join()
    send_conn.close()

    return (t1 - t0) / 1e9


# --- 3. multiprocessing.Queue (Pipe + Feeder Thread + Lock + pickle)
def _queue_consumer(
    q: Queue[tuple[int, int, int, int]],
    n_ticks: int,
    ready_ev: EventT,
    done_ev: EventT,
) -> None:
    """Consume pickled tuples from multiprocessing.Queue."""
    ready_ev.set()
    count: int = 0
    while count < n_ticks:
        _ = q.get()
        count += 1
    done_ev.set()


def benchmark_queue(n_ticks: int) -> float:
    """Run producer-consumer throughput benchmark using multiprocessing.Queue."""
    q: Queue[tuple[int, int, int, int]] = mp.Queue(maxsize=50_000)
    ready_ev: EventT = Event()
    done_ev: EventT = Event()

    proc: Process = Process(
        target=_queue_consumer,
        args=(q, n_ticks, ready_ev, done_ev),
        daemon=True,
    )
    proc.start()
    ready_ev.wait()

    tick = (50_000_00, 1_000, 1_700_000_000, 1)

    t0: int = time.perf_counter_ns()
    for _ in range(n_ticks):
        q.put(tick)

    done_ev.wait()
    t1: int = time.perf_counter_ns()
    proc.join()

    return (t1 - t0) / 1e9


# ------ Runner & Formatted Summary ------
def run_all_benchmarks() -> None:
    """Execute all IPC benchmarks and print comparative performance metrics."""
    # 1,000,000 ticks for high-speed IPC; 200,000 for queue to avoid excessive timeouts
    N_TICKS_FAST: int = 1_000_000
    N_TICKS_QUEUE: int = 200_000

    print("=" * 82)
    print(
        f"IPC BENCHMARK: Streaming {N_TICKS_FAST:,} market ticks (32 bytes payload)"
    )
    print("=" * 82)

    # 1. Imprint MarketDataStream
    print("[1/3] Benchmarking Imprint MarketDataStream (SHM RingBuf)...")
    t_shm = benchmark_shm_ringbuf(N_TICKS_FAST)
    rate_shm = N_TICKS_FAST / t_shm

    # 2. multiprocessing.Pipe
    print("[2/3] Benchmarking multiprocessing.Pipe (socketpair + pickle)...")
    t_pipe = benchmark_pipe(N_TICKS_FAST)
    rate_pipe = N_TICKS_FAST / t_pipe

    # 3. multiprocessing.Queue
    print(
        f"[3/3] Benchmarking multiprocessing.Queue ({N_TICKS_QUEUE:,} ticks)..."
    )
    t_queue = benchmark_queue(N_TICKS_QUEUE)
    rate_queue = N_TICKS_QUEUE / t_queue

    # Display comparison table
    results = [
        (
            "Imprint SHM RingBuf",
            t_shm,
            rate_shm,
            (t_shm / N_TICKS_FAST) * 1e9,
            1.0,
        ),
        (
            "multiprocessing.Pipe",
            t_pipe,
            rate_pipe,
            (t_pipe / N_TICKS_FAST) * 1e9,
            rate_shm / rate_pipe,
        ),
        (
            "multiprocessing.Queue",
            t_queue,
            rate_queue,
            (t_queue / N_TICKS_QUEUE) * 1e9,
            rate_shm / rate_queue,
        ),
    ]

    print("\n" + "=" * 82)
    print(
        f"{'IPC Mechanism':<28} | {'Elapsed (s)':<11} | {'Throughput (msg/s)':<18} | {'Latency':<10} | {'Speedup'}"
    )
    print("-" * 82)
    for name, elapsed, throughput, lat_ns, speedup in results:
        speedup_str = f"{speedup:.1f}x slower" if speedup > 1.0 else "Baseline"
        print(
            f"{name:<28} | {elapsed:>11.4f} | {throughput:>18,.0f} | {lat_ns:>7.1f} ns | {speedup_str}"
        )
    print("=" * 82)


if __name__ == "__main__":
    run_all_benchmarks()
