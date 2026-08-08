---
name: resource-semaphore-v1-3
description: Generates Python concurrency code using version v1.3.* of the resource-semaphore library to apply multi-resource backpressure. Use this when the user needs to manage constrained resources like CPU, RAM, or DB connections across threads or asyncio tasks.
---

# Resource Semaphore Skill

When asked to implement rate-limiting, resource constraints, or backpressure using `resource-semaphore`, follow these strict guidelines and patterns:

## Core Concepts & Classes
- **Sync vs Async**: Use `ResourceSemaphore` for threaded/synchronous code, and `AsyncResourceSemaphore` for `asyncio` code.
- **Initialization**: You must initialize the semaphore with a dictionary of resources. Capacities must be positive numbers. Empty dictionaries raise a `ValueError`.
  ```python
  from resource_semaphore import AsyncResourceSemaphore

  semaphore = AsyncResourceSemaphore(resources={"db_conn": 2, "ram_mb": 4096})
  ```
- **Fairness & Infinite Bypass**: The standard semaphore uses an intelligent FIFO queue by default. While it prioritizes older requests to prevent starvation, it natively evaluates the entire queue and automatically allows smaller tasks to safely bypass blocked heavy tasks if leftover capacity permits. This totally eliminates head-of-line blocking deadlocks.
  ```python
  # Even if a task is blocked waiting for 10 CPU cores,
  # a smaller task needing only 1 CPU core can immediately bypass it if available.
  semaphore = AsyncResourceSemaphore({"cpu": 10})
  ```
- **Greedy Variants**: If strict fairness is not required and starvation is unlikely, use the hyper-optimized `GreedyResourceSemaphore` or `AsyncGreedyResourceSemaphore`. These variants skip queue tracking entirely and allow tasks to aggressively acquire resources the instant they become available, regardless of queue position.
  ```python
  from resource_semaphore import AsyncGreedyResourceSemaphore

  greedy_sem = AsyncGreedyResourceSemaphore({"cpu": 10})
  ```

## 1. Always Prefer the `.claim()` Context Manager
The safest way to acquire resources is using the `.claim()` context manager, which handles cleanup automatically even if exceptions occur.

**Asynchronous Pattern:**
```python
async with semaphore.claim({"db_conn": 1, "ram_mb": 500}):
    await do_work()
```

**Synchronous Pattern:**
```python
with semaphore.claim({"db_conn": 1, "ram_mb": 500}):
    do_work()
```

## 2. Handling Timeouts
To avoid indefinite blocking, `.claim()` and `.acquire()` accept a `timeout` argument (in seconds). If the timeout is reached, the library raises a `TimeoutError`. You must handle this explicitly:
```python
try:
    async with semaphore.claim({"cpu": 1}, timeout=5.0):
        await process()
except TimeoutError:
    print("Failed to acquire resources in time.")
```

## 3. Manual Acquire and Release (Use with Caution)
If you cannot use `.claim()`, you may use `.acquire()`. It returns an opaque `Ticket` object. You **must** release this exact ticket in a `finally` block to prevent leaks.
```python
ticket = await semaphore.acquire({"db_conn": 1})
try:
    await do_work()
finally:
    await semaphore.release(ticket)
```

## 4. System Utilities Integration
If the user wants to dynamically set capacities based on system hardware, use the `utils` extension. Ensure you import from `resource_semaphore.utils`.
- **Sync**: `get_cpu(logical=False)`, `get_memory()`, `get_storage("/")`
- **Async**: `aget_cpu()`, `aget_memory()`, `aget_storage()`

```python
from resource_semaphore.utils import get_cpu, get_memory

semaphore = ResourceSemaphore(
    resources={
        "cpu_cores": get_cpu(),
        "ram_bytes": get_memory(),
    }
)
```

## 5. Testing
When generating unit tests for logic that uses a semaphore, use the no-op variants `NoopResourceSemaphore` or `AsyncNoopResourceSemaphore`. These bypass all limits and do not block.
