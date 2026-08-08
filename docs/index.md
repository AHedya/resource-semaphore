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

> **Note:** By default, `acquire()` and `claim()` block until the requested resources become available, maintaining a strict FIFO queue to guarantee fairness. You can optionally provide a `timeout` (in seconds) to fail fast with a `TimeoutError`.

## Fairness, Infinite Bypass, and Greedy Semaphores

By default, `ResourceSemaphore` and `AsyncResourceSemaphore` use an intelligent **Infinite Bypass** fairness model. While they prioritize older requests to prevent starvation, they automatically evaluate the *entire* queue and allow any smaller tasks to safely bypass blocked heavy tasks if leftover capacity permits. This massive improvement over strict head-of-line blocking prevents pipelines from deadlocking without requiring any manual window configuration.

```python
from resource_semaphore import AsyncResourceSemaphore

# Even if a massive task is blocked waiting for 10 CPU cores,
# a smaller task needing only 1 CPU core can immediately bypass it if available.
semaphore = AsyncResourceSemaphore({"cpu": 10})
```

For workloads where starvation is unlikely, you can use the hyper-optimized Greedy variants:
- `GreedyResourceSemaphore`
- `AsyncGreedyResourceSemaphore`

These skip queue bookkeeping entirely, allowing tasks to aggressively acquire resources the instant they become available, regardless of queue position.

## Sync vs Async

The package provides two primary classes:
- `ResourceSemaphore`: For synchronous multi-threaded applications. Uses a per-waiter `threading.Event` registry internally.
- `AsyncResourceSemaphore`: For asynchronous `asyncio` applications. Uses a per-waiter `asyncio.Event` registry internally.

Both share identical APIs (modulo `async`/`await`).

## Initialization

You initialize a semaphore by providing a dictionary of resource names to their capacities. All capacities must be positive numbers (integers or floats).

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
