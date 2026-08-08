"""Sequential Workers Example

Demonstrates how resource-semaphore enforces sequential execution when
a resource is constrained to a single unit. Even though tasks are
submitted to a thread pool concurrently, only one can hold the
'cpu_slots' resource at a time.
"""

import time
from concurrent.futures import ThreadPoolExecutor
from typing import Literal

from resource_semaphore import ResourceSemaphore

# Define resource keys for type safety (optional)
Keys = Literal["cpu_slots", "RAM_MB"]
resources: dict[Keys, int] = {"cpu_slots": 1, "RAM_MB": 312}
semaphore = ResourceSemaphore[Keys](resources=resources)

WORK_TIME = 0.4
NUM_TASKS = 5


def run(task_id: int):
    """Simulate a CPU-bound task."""
    print(f"  [Worker {task_id}] Started.")
    time.sleep(WORK_TIME)
    print(f"  [Worker {task_id}] Finished.")


def main():
    # With only 1 cpu_slots resource, workers run one at a time
    # even though the thread pool has 5 workers available.
    # Try increasing cpu_slots to see parallel execution.
    print("[Main] Submitting 5 tasks to a pool of 5 workers...")

    def bound_task(task_id: int):
        with semaphore.claim({"cpu_slots": 1}):
            run(task_id)

    begin = time.monotonic()
    with ThreadPoolExecutor(max_workers=5) as pool:
        futures = [pool.submit(bound_task, task_id=i + 1) for i in range(NUM_TASKS)]
        for f in futures:
            f.result()  # wait for completion and propagate exceptions

    elapsed = time.monotonic() - begin
    print(f"[Main] All tasks finished in {elapsed:.2f}s.")
    print(
        f"[Main] Expected >= {NUM_TASKS * WORK_TIME:.2f}s (sequential due to cpu_slots=1)."
    )


if __name__ == "__main__":
    main()
