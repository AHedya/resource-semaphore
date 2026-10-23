# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.4.1] - 2026-10-23

### Fixed
- **Free-Threaded Lost Wakeup Race**: Moved `waiter.event.clear()` inside the semaphore lock critical section in `ResourceSemaphore` and `AsyncResourceSemaphore` to prevent lost wakeups under free-threaded CPython (GIL-disabled) and high thread contention.
- **Bypass Fairness Test Determinism**: Fixed race in `test_small_request_bypasses_blocked_large_waiter` across sync and async test suites by isolating partial capacity releases, and replaced brittle wall-clock sleeps with deterministic lock-queue polling handshakes.
- **Type Checking**: Narrowed regex match in Nox coverage calculation to satisfy static type checkers (`pyrefly`).

### Added
- **Top-Level Package Exports**: Exported `Ticket`, `SemaphoreError`, `BaseResourceSemaphore`, and `BaseAsyncResourceSemaphore` directly from the `resource_semaphore` package root.
- **OS Classifiers**: Added explicit Trove classifiers for `POSIX :: Linux`, `Microsoft :: Windows`, and `MacOS`.

## [1.4.0] - 2026-10-23

### Added
- **Python 3.15, 3.15t & 3.13t Support**: Officially added support and CI validation for Python 3.15, free-threaded Python 3.15t, and free-threaded Python 3.13t.
- **Cross-Platform Utilities**: Hardened `get_storage()` to resolve the drive root anchor on Windows, and hardened `get_cpu()` to guarantee returning a positive `int` via cascading fallbacks for containerized environments.
- **On-Demand Pre-Push Checklist**: Added `nox -s prepush` to run local linting, type-checking, all test suites in parallel, and coverage badge verification.

### Changed
- **CI Optimization**: Streamlined GitHub Actions tests into a single-runner parallel execution job with `uv` and `nox -j`, significantly reducing workflow execution time.
- **Pre-commit Refinement**: Restricted git `pre-commit` hook to fast static analysis (linting and type-checking in ~1s), removing mutating coverage tasks from commits.
- **Python Version Constraint**: Relaxed `requires-python` from `<3.15,>=3.11` to `<3.16,>=3.11`.

### Fixed
- **Sequence Ordering Race**: Atomically allocate sequence counters and register waiters under lock in `ResourceSemaphore` and `AsyncResourceSemaphore` to prevent out-of-order sequence insertion under thread contention.

### Changed
- **Lock Consolidation**: Streamlined lock acquisition in `acquire()` by evaluating the fast-path and registering waiters in a single synchronized critical section.
- **Documentation**: Clarified snapshot semantics of the `available` diagnostic property in documentation.

## [1.3.0] - 2026-08-09

### Changed
- **Queue Fairness**: Eliminated the hardcoded `lookahead_window` parameter. Semaphores now evaluate the entire queue on each check, rather than a fixed lookahead window. This allows smaller requests to bypass blocked heavy requests when capacity permits, without requiring manual window configuration.
- **Hot-path Optimization**: Refactored `acquire()` loops across all classes with an $O(1)$ fast-path, stripping away redundant waiter allocation and bookkeeping overhead for uncontended acquisitions.

> We've evaluated a Numpy-backed variation on commit `34c13bab13b6c966caaea441a4f3e1fd48efcb73`, but it was purged due to poor performance.

## [1.2.0] - 2026-08-08

### Added
- **Lookahead Window (`lookahead_window`)**: `ResourceSemaphore` and `AsyncResourceSemaphore` now accept a `lookahead_window` parameter (default: 1). This allows smaller queued requests to safely bypass blocked heavy requests, eliminating pipeline deadlocks and maximizing utilization.
- **Greedy Variants**: Introduced `GreedyResourceSemaphore` and `AsyncGreedyResourceSemaphore` for workloads that require aggressive resource acquisition without queue fairness (skips head-of-line blocking entirely).

### Changed
- **Performance (Thundering Herd Mitigation)**: Overhauled the internal concurrency notification mechanism. Replaced the shared `Condition.notify_all()` broadcast with a lightweight, per-waiter `Event` registry. Semaphores now selectively wake only eligible waiters, drastically reducing spurious wakeups and context switches under heavy concurrency.
