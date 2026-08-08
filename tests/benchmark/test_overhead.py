import asyncio
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor

import pytest
from pytest_benchmark.fixture import BenchmarkFixture

from resource_semaphore.asynchronous import (
    AsyncGreedyResourceSemaphore,
    AsyncResourceSemaphore,
)
from resource_semaphore.base import BaseAsyncResourceSemaphore, BaseResourceSemaphore
from resource_semaphore.synchronous import (
    GreedyResourceSemaphore,
    ResourceSemaphore,
)

WORK_TIME = 0

RESOURCES = {"cpu": 32}
TASKS = [1_000, 3_000, 5_000, 10_000]
TASKS_IDS = [f"{x // 1000}K" for x in TASKS]

SYNC_WORKERS = [16, 64, 128]
ITERATIONS = 1
ROUNDS = 5


@pytest.mark.parametrize(
    "max_workers", SYNC_WORKERS, ids=[f"{w}w" for w in SYNC_WORKERS]
)
@pytest.mark.parametrize("tasks", TASKS, ids=TASKS_IDS)
@pytest.mark.parametrize(
    "semaphore_factory",
    [
        lambda: GreedyResourceSemaphore(resources=RESOURCES),
        lambda: ResourceSemaphore(resources=RESOURCES),
    ],
    ids=["Greedy", "Fair"],
)
def test_sync_workload(
    benchmark: BenchmarkFixture,
    semaphore_factory: Callable[[], BaseResourceSemaphore],
    max_workers: int,
    tasks: int,
):
    semaphore = semaphore_factory()

    def bench():
        def worker():
            with semaphore.claim({"cpu": 1}):
                pass

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            list(executor.map(lambda _: worker(), range(tasks)))

    benchmark.pedantic(target=bench, iterations=ITERATIONS, rounds=ROUNDS)


@pytest.mark.parametrize("tasks", TASKS, ids=TASKS_IDS)
@pytest.mark.parametrize(
    "semaphore_factory",
    [
        lambda: AsyncGreedyResourceSemaphore(resources=RESOURCES),
        lambda: AsyncResourceSemaphore(resources=RESOURCES),
    ],
    ids=["Greedy", "Fair"],
)
def test_async_overhead(
    benchmark: BenchmarkFixture,
    semaphore_factory: Callable[[], BaseAsyncResourceSemaphore],
    tasks: int,
):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    semaphore = semaphore_factory()

    async def bench():
        async def worker():
            async with semaphore.claim({"cpu": 1}):
                pass

        await asyncio.gather(*(worker() for _ in range(tasks)))

    def sync_wrapper():
        loop.run_until_complete(bench())

    benchmark.pedantic(target=sync_wrapper, iterations=ITERATIONS, rounds=ROUNDS)

    loop.close()
