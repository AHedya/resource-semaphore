# Resource Semaphore Documentation

Resource Semaphore is a typed, high-level synchronization library for managing multiple constrained resources within a single process. It applies backpressure to prevent resource exhaustion.

## Installation

```bash
pip install resource-semaphore
```

Or with [uv](https://docs.astral.sh/uv/):

```bash
uv add resource-semaphore
```

## Core Concepts

A standard semaphore guards a single counter — for example, "at most 5 concurrent connections." `resource-semaphore` generalizes this to **multiple, heterogeneous resources** with continuous capacities.

For example, your application might be constrained by both "CPU cores" and "available RAM." This library lets you model limits on these resources and apply backpressure to consumers requesting them. When a consumer calls `acquire()` or enters a `claim()` block, it will block until **all** requested resources are simultaneously available.

> **Note:** By default, `acquire()` and `claim()` block until the requested resources become available. Requests are served in priority order — the earliest-arrived request that *can currently be satisfied* goes first — but a smaller, later request may be granted ahead of an earlier, larger one that doesn't fit yet. This is not strict FIFO; see [Fairness and Trade-offs](#fairness-and-trade-offs) below. You can optionally provide a `timeout` (in seconds) to fail fast with a `TimeoutError`.

## Fairness and Trade-offs

`ResourceSemaphore` and `AsyncResourceSemaphore` use a priority model: the earliest-arrived waiter whose demand currently fits is granted first, but a later, smaller request may bypass an earlier, larger one that can't yet be satisfied. This avoids one common failure mode (a large blocked request stalling every smaller request behind it) at the cost of a different one: a sufficiently large request can wait longer than it would under strict FIFO if smaller requests keep arriving. There's no upper bound on that wait under sustained load — if your workload has occasional large demands mixed with a constant stream of small ones, expect the large ones to be delayed accordingly.

`GreedyResourceSemaphore`/`AsyncGreedyResourceSemaphore` skip ordering entirely: any caller whose demand fits wins, including a caller that arrived after another one is already waiting. This is a materially different (and stronger) starvation risk than the Fair variant's: a queued waiter can be starved indefinitely by a continuous stream of new callers, not just delayed. Use Greedy only when every request is roughly the same size and you don't need any specific request to be guaranteed forward progress.

Fair and Greedy variants show no measurable throughput difference in our benchmarks (see `.benchmarks/`); Greedy trades ordering guarantees for a simpler code path, not raw speed.

## Sync vs Async

The package provides two primary classes:
- `ResourceSemaphore`: For synchronous multi-threaded applications. Uses a per-waiter `threading.Event` registry internally.
- `AsyncResourceSemaphore`: For asynchronous `asyncio` applications. Uses a per-waiter `asyncio.Event` registry internally.

Both share identical APIs (modulo `async`/`await`).

## Initialization

You initialize a semaphore by providing a dictionary of resource names to their capacities. All capacities must be positive integers (`int`).

```python
from resource_semaphore import AsyncResourceSemaphore

semaphore = AsyncResourceSemaphore(resources={"db_conn": 2, "ram_mb": 4096})
```

An empty resources dictionary or a zero/negative capacity will raise a `ValueError`.

## Generic Typing

Both semaphore classes are generic over their resource key type. You can use `typing.Literal` to get compile-time checks on resource names:

```python
from typing import Literal
from resource_semaphore import ResourceSemaphore

Keys = Literal["db_conn", "ram_mb"]
resources: dict[Keys, int] = {"db_conn": 2, "ram_mb": 4096}

semaphore = ResourceSemaphore[Keys](resources=resources)

# Type checkers will flag this as an error:
# semaphore.acquire({"typo": 1})
```

If you don't need strict key typing, you can omit the type parameter entirely.

## The `claim` Context Manager

The easiest and safest way to acquire and release resources is using the `claim` context manager. It blocks until the requested resources are available, acquires them, and guarantees they are released when the block exits — even if an exception is raised.

### Asynchronous Example

```python
async def process_data(semaphore, data_size_mb):
    # Blocks until 1 DB connection and data_size_mb RAM are available
    # An optional timeout can be provided: timeout=5.0
    async with semaphore.claim({"db_conn": 1, "ram_mb": data_size_mb}):
        await do_work()
    # Resources are automatically released here
```

### Synchronous Example

```python
def process_data_sync(semaphore, data_size_mb):
    # Blocks until 1 DB connection and data_size_mb RAM are available
    # An optional timeout can be provided: timeout=5.0
    with semaphore.claim({"db_conn": 1, "ram_mb": data_size_mb}):
        do_work()
    # Resources are automatically released here
```

## Manual Acquire and Release

If you need more fine-grained control, you can use `.acquire()` and `.release()` directly. Always pair them in a `try`/`finally` block to avoid resource leaks.

```python
ticket = await semaphore.acquire({"db_conn": 1}, timeout=10.0)
try:
    await do_work()
finally:
    await semaphore.release(ticket)
```

## Shutdown

You can gracefully shut down a semaphore to signal that no further work should be processed. Calling `shutdown()` will:

1. Set `is_shutdown` to `True`.
2. Wake all callers currently blocked in `acquire()`, causing them to raise `SemaphoreError`.
3. Cause any subsequent `acquire()` calls to raise `SemaphoreError` immediately.

```python
from resource_semaphore import AsyncResourceSemaphore
from resource_semaphore.base import SemaphoreError

semaphore = AsyncResourceSemaphore(resources={"db_conn": 2})

# Later, when shutting down:
await semaphore.shutdown()

# Any blocked or future acquire will raise:
try:
    await semaphore.acquire({"db_conn": 1})
except SemaphoreError:
    print("Semaphore has been shut down")
```

`shutdown()` is idempotent — calling it multiple times is safe.

## No-op Variants

For testing scenarios where you want to bypass resource limits entirely, use the no-op implementations:

- `NoopResourceSemaphore` (synchronous)
- `AsyncNoopResourceSemaphore` (asynchronous)

These accept any `acquire()` / `release()` call without blocking and report empty capacity. They're useful for unit tests where resource contention isn't relevant.

```python
from resource_semaphore import NoopResourceSemaphore

# In production:
semaphore = ResourceSemaphore(resources={"db_conn": 2})

# In tests:
semaphore = NoopResourceSemaphore()
```

## Validation & Error Handling

The semaphore validates inputs eagerly:

| Condition | Error |
|-----------|-------|
| Empty resources dict on init | `ValueError` |
| Zero or negative capacity on init | `ValueError` |
| Unknown resource name in acquire/release | `ValueError` |
| Demand exceeds total capacity | `ValueError` |
| Zero or negative demand | `ValueError` |
| Release would exceed capacity (double-release) | `ValueError` |
| Acquire on a shut-down semaphore | `SemaphoreError` |

## Diagnostics

You can inspect the current state at any time. Both `capacity` and `available` return snapshot copies, so they won't be affected by concurrent modifications.

```python
print(semaphore.capacity)
# {'db_conn': 2, 'ram_mb': 4096}

print(semaphore.available)
# {'db_conn': 1, 'ram_mb': 3000}

print(semaphore.is_shutdown)
# False
```

> **Note:** `available` is not read under lock — it's intended for diagnostics and logging, not for making synchronization decisions.

## System Utilities

The package provides a `utils` extension that helps automatically discover the host machine's physical capabilities. This is particularly useful for dynamically setting up your semaphore capacities.

To use the utilities, you must install the `utils` extra, which brings in `psutil`:
```bash
pip install "resource-semaphore[utils]"
```

Then you can use the synchronous or asynchronous helper functions:

```python
from resource_semaphore.utils import get_cpu, get_memory, get_storage
from resource_semaphore import ResourceSemaphore

semaphore = ResourceSemaphore(
    resources={
        "cpu_cores": get_cpu(logical=False),
        "ram_bytes": get_memory(),
        "disk_free_bytes": get_storage("/"),
    }
)
```

Async variants (`aget_cpu`, `aget_memory`, `aget_storage`) are also available if you are discovering resources during application startup in an async context.

## Limitations

- **Single-Process Scope:** `resource-semaphore` operates purely within a single Python process (threads or `asyncio`). It does not provide inter-process communication (IPC) or distributed multi-node resource locking.
- **Resource Discovery Boundaries:** The `utils` extra provides hardware capacity helpers strictly for CPU count, system RAM, and disk storage via `psutil`. It does not discover GPU availability, network bandwidth, or peripheral hardware. Users may manually define any custom resource key with integer units.
- **Application Deadlocks:** The library tracks resource capacities, not task dependency chains. If application code acquires multiple semaphores out-of-order across threads/tasks, deadlocks may still occur at the application level.
- **API Stability:** Pre-1.0 / active development status means minor version updates may occasionally include breaking API changes.

