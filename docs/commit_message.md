feat: introduce numpy backend and infinite bypass fairness (v1.3.0)

- feat: added `resource_semaphore.np` subpackage with `NumpyResourceSemaphore` and `AsyncNumpyResourceSemaphore` for matrix-based $O(1)$ Python-time queue resolution under heavy contention.
- feat: added optional installation extras `[numpy]` and `[all]`.
- refactor: eliminated the hardcoded `lookahead_window` parameter in favor of an **Infinite Bypass** fairness model. Semaphores now evaluate the entire queue perfectly, automatically allowing smaller requests to safely bypass blocked heavy requests.
- perf: introduced an $O(1)$ fast-path in `acquire()` across all semaphore classes to bypass redundant waiter allocation on uncontended acquisitions.
- docs: updated `README.md`, `docs/index.md`, `CHANGELOG.md`, and `TODO.md` to document the new v1.3.0 architecture and Numpy capabilities.
- test: parameterized standard test suites to validate both native and numpy implementations seamlessly.