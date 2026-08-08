feat: introduce greedy semaphores, lookahead windows, and shared-base architecture

- Added `GreedyResourceSemaphore` and `AsyncGreedyResourceSemaphore` to allow tasks to bypass queueing entirely for maximum utilization when fairness is not required.
- Bumped minor version
- Implemented `lookahead_window` in `ResourceSemaphore` and `AsyncResourceSemaphore` (defaults to 1 for strict FIFO). Setting a larger window allows smaller queued tasks to bypass heavy blocked tasks if their demands fit within the leftover capacity, resolving head-of-line deadlocks while bounding starvation.
- Restructured `synchronous.py` and `asynchronous.py` using a template Shared-Base class pattern (`_SyncBaseSemaphore`, `_AsyncBaseSemaphore`). This hoists all boilerplate operations (lock management, capacity validation, shutdown checks) into the base classes.
- Stripped all sequence counting, list appending, and queue indexing overhead from the Greedy implementations, creating hyper-optimized acquisition loops.
- Eliminated redundant test boilerplate by unifying fair and greedy bypass tests with `@pytest.mark.parametrize`.
- Updated `README.md` and `docs/index.md` to document the new `lookahead_window` and Greedy features.