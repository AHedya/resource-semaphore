# Resource Semaphore

![License](https://img.shields.io/badge/License-Apache--2.0-blue.svg)
![Python](https://img.shields.io/badge/Python-3.11%20%7C%203.12%20%7C%203.13%20%7C%203.14%20%7C%203.14t-blue.svg)
![Coverage](https://img.shields.io/badge/Coverage-82%25-yellowgreen.svg)


**Resource Semaphore** is a typed, high-level synchronization library for managing multiple constrained resources within a single process. It applies backpressure to prevent resource exhaustion.

Standard semaphores guard a single counter of "slots." `resource-semaphore` extends this to **multiple, heterogeneous resources**: such as CPU cores, available RAM, disk I/O bandwidth, or worker slots: with a single, atomic acquire/release operation. When capacity is exhausted, callers block until resources become available.

> **What's New in v1.2.0**: We overhauled the concurrency model to prevent "thundering herd" bottlenecks using a per-waiter event pattern! See the [Changelog](CHANGELOG.md) for details.

## Installation

```bash
pip install resource-semaphore
```

## Quick Start

```python
import asyncio
from resource_semaphore import AsyncResourceSemaphore

semaphore = AsyncResourceSemaphore(resources={"db_conn": 2, "ram_mb": 4096})


async def process(data_size_mb: float):
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

- **Multi-resource**: manage DB connection, RAM, workers, or any named resource in a single semaphore
- **Sync + Async**: `ResourceSemaphore` for threads, `AsyncResourceSemaphore` for asyncio
- **Fairness & Lookahead**: Avoids starvation by enforcing strict head-of-line blocking, with a configurable `lookahead_window` (default: 1) that allows smaller queued requests to safely bypass heavy blocked tasks, drastically improving throughput.
- **Greedy Variants**: `GreedyResourceSemaphore` and `AsyncGreedyResourceSemaphore` skip queueing entirely for maximum utilization in non-starving pipelines.
- **High Performance**: Built on a shared template base class architecture, heavily optimizing acquisition loops by stripping unnecessary overhead from greedy implementations.
- **Timeouts**: abort waits gracefully using `timeout` arguments
- **Safe Releases**: opaque `Ticket` objects prevent corrupted state from incorrect releases
- **Typed**: generic over resource key types via `Literal` for compile-time safety
- **No-op variants**: `NoopResourceSemaphore` and `AsyncNoopResourceSemaphore` for tests
- **Graceful shutdown**: `shutdown()` wakes all blocked callers with a `SemaphoreError`
- **Zero dependencies** (Core): pure Python, nothing to install beyond the standard library
- **System Utilities**: dynamic initialization via `resource-semaphore[utils]` for fetching CPU/RAM limits



## Documentation

For a comprehensive guide on core concepts, initialization, and API usage (including both synchronous and asynchronous context managers), please refer to our documentation:

- **[Docs: Basic Features & API Usage](docs/index.md)**

## Examples

We provide runnable scripts demonstrating real-world usage scenarios:

- **[Runnable Examples](examples/)**

## Roadmap

To see what features are planned for future releases and what has already been accomplished, check out our [TODO.md](docs/TODO.md) tracker.