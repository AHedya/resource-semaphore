import asyncio
import threading
import time

from resource_semaphore.asynchronous import AsyncResourceSemaphore
from resource_semaphore.synchronous import ResourceSemaphore


def sync_worker(semaphore: ResourceSemaphore, worker_id: int):
    print(f"Sync Worker {worker_id}: Waiting for resources...")
    # Claim 1 DB connection and 500 MB RAM
    with semaphore.claim({"db_conn": 1, "ram_mb": 500}):
        print(f"Sync Worker {worker_id}: Acquired resources! Working...")
        time.sleep(1)
    print(f"Sync Worker {worker_id}: Released resources.")


def run_sync_example():
    print("Running Synchronous Example")
    semaphore = ResourceSemaphore({"db_conn": 2, "ram_mb": 2048})

    threads = []
    # Start 3 workers, but we only have 2 DB connections, so one will have to wait
    for i in range(3):
        t = threading.Thread(target=sync_worker, args=(semaphore, i))
        threads.append(t)
        t.start()

    for t in threads:
        t.join()


# Asynchronous Example


async def async_worker(semaphore: AsyncResourceSemaphore, worker_id: int):
    print(f"Async Worker {worker_id}: Waiting for resources...")
    # Claim 1 DB connection and 500 MB RAM
    async with semaphore.claim({"db_conn": 1, "ram_mb": 500}):
        print(f"Async Worker {worker_id}: Acquired resources! Working...")
        await asyncio.sleep(1)
    print(f"Async Worker {worker_id}: Released resources.")


async def run_async_example():
    print("\nRunning Asynchronous Example")
    semaphore = AsyncResourceSemaphore({"db_conn": 2, "ram_mb": 2048})

    # Start 3 workers concurrently, one will have to wait for a DB connection
    tasks = [asyncio.create_task(async_worker(semaphore, i)) for i in range(3)]
    await asyncio.gather(*tasks)


if __name__ == "__main__":
    run_sync_example()
    asyncio.run(run_async_example())
