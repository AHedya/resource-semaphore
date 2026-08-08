# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.2.0] - 2026-08-08

### Added
- **Lookahead Window (`lookahead_window`)**: `ResourceSemaphore` and `AsyncResourceSemaphore` now accept a `lookahead_window` parameter (default: 1). This allows smaller queued requests to safely bypass blocked heavy requests, eliminating pipeline deadlocks and maximizing utilization.
- **Greedy Variants**: Introduced `GreedyResourceSemaphore` and `AsyncGreedyResourceSemaphore` for workloads that require aggressive resource acquisition without queue fairness (skips head-of-line blocking entirely).

### Changed
- **Performance (Thundering Herd Mitigation)**: Overhauled the internal concurrency notification mechanism. Replaced the shared `Condition.notify_all()` broadcast with a lightweight, per-waiter `Event` registry. Semaphores now selectively wake only eligible waiters, drastically reducing spurious wakeups and context switches under heavy concurrency.
