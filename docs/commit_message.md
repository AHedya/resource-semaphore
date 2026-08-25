fix: atomic sequence counter allocation and lock consolidation (v1.3.1)

- fix: atomically allocate sequence counters and register waiters under lock in `ResourceSemaphore` and `AsyncResourceSemaphore` to prevent out-of-order sequence insertion under thread contention.
- perf: streamline lock entry in `acquire()` by checking the fast path and registering waiters in a single synchronized critical section.
- test: add explicit tests for `_is_first_eligible()` precedence checks and fallback branches, achieving 100% statement coverage across all core modules.
- docs: clarify snapshot semantics of `available` property diagnostics in `docs/index.md`.
- chore: remove temporary scratch file `tst.py`.