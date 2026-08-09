# Resource Semaphore

![License](https://img.shields.io/badge/License-Apache--2.0-blue.svg)
![Python](https://img.shields.io/badge/Python-3.11%20%7C%203.12%20%7C%203.13%20%7C%203.14%20%7C%203.14t-blue.svg)
![Coverage](https://img.shields.io/badge/Coverage-98%25-brightgreen.svg)


**Resource Semaphore** is a typed, high-level synchronization library for managing multiple constrained resources within a single process. It applies backpressure to prevent resource exhaustion.

Standard semaphores guard a single counter of "slots." `resource-semaphore` extends this to **multiple, heterogeneous resources**: such as CPU cores, available RAM, disk I/O bandwidth, or worker slots: with a single, atomic acquire/release operation. When capacity is exhausted, callers block until resources become available.
## Installation

```bash
pip install resource-semaphore
```

## Quick Start

```python
import asyncio
from resource_semaphore import AsyncResourceSemaphore

semaphore = AsyncResourceSemaphore(resources={"db_conn": 2, "ram_mb": 4096})


async def process(data_size_mb: int):
    async with semaphore.claim({"db_conn": 1, "ram_mb": data_size_mb}):
        await do_work()


async def main():
    # Three tasks compete for 2 DB connections: one will wait automatically
    await asyncio.gather(
        process(1024),
        process(1024),
        process(1024),
    )
```

## Features

- **Multi-resource**: atomically acquire multiple named resources (e.g. DB connections, RAM, workers) in one call
- **Sync + Async**: `ResourceSemaphore` (threading) and `AsyncResourceSemaphore` (asyncio) share the same API
- **Fair and Greedy variants**: Fair semaphores wake the earliest-arrived request that can currently be satisfied, and let smaller later requests bypass a blocked larger one — see [Docs: Fairness and Trade-offs](docs/index.md#fairness-and-trade-offs) for the starvation trade-off this implies. Greedy semaphores skip ordering entirely and grant to whichever caller wins the race; this can starve a specific waiter indefinitely under sustained contention (see [Docs: Fairness and Trade-offs](docs/index.md#fairness-and-trade-offs)).
- **Timeouts**: `acquire()`/`claim()` accept an optional `timeout` argument and raise `TimeoutError`
- **Safe releases**: opaque `Ticket` objects; releasing an unknown or already-released ticket raises `ValueError`
- **Typed**: generic over resource key types via `Literal` for compile-time safety
- **No-op variants**: `NoopResourceSemaphore` and `AsyncNoopResourceSemaphore` for tests that don't need real limits
- **Graceful shutdown**: `shutdown()` wakes all blocked callers with `SemaphoreError`; further `acquire()` calls raise immediately
- **Zero dependencies** in core
- **Optional system utilities**: `resource-semaphore[utils]` wraps `psutil` for CPU/RAM/disk capacity discovery (CPU and RAM only — no GPU support)
- **Performance**: Fair and Greedy variants show no measurable throughput difference in our benchmarks (see `.benchmarks/`); Greedy trades ordering guarantees for a simpler code path, not raw speed.

## Limitations

- **Single-process only**: Manages concurrency within a single Python process (threads or `asyncio` tasks). It is not a distributed or cross-process semaphore.
- **Resource discovery limits**: Built-in utilities (`resource-semaphore[utils]`) only discover basic CPU, memory, and disk metrics via `psutil`. There is no automatic discovery for GPUs, network interfaces, or custom external hardware (though any named resource can be managed by manually specifying integer capacities).
- **No deadlock prevention**: Does not detect or prevent application-level deadlocks resulting from improper lock acquisition ordering across multiple semaphores or code paths.
- **Evolving API**: The API is subject to refinement; minor version updates may introduce breaking changes as feature needs evolve.



## Documentation

For a comprehensive guide on core concepts, initialization, and API usage (including both synchronous and asynchronous context managers), please refer to our documentation:

- **[Docs: Basic Features & API Usage](docs/index.md)**

## Examples

We provide runnable scripts demonstrating real-world usage scenarios:

- **[Runnable Examples](examples/)**

## Roadmap

To see what features are planned for future releases and what has already been accomplished, check out our [TODO.md](docs/TODO.md) tracker.