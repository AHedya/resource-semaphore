feat: infinite bypass fairness & hot-path optimizations (v1.3.0)

- refactor: eliminated the hardcoded `lookahead_window` parameter in favor of an **Infinite Bypass** fairness model. Semaphores now evaluate the entire queue perfectly, automatically allowing smaller requests to safely bypass blocked heavy requests. This completely eliminates head-of-line blocking deadlocks.
- perf: introduced an $O(1)$ fast-path in `acquire()` across all semaphore classes to bypass redundant waiter allocation on uncontended acquisitions.
- docs: updated `README.md`, `docs/index.md`, `CHANGELOG.md`, and `TODO.md` to document the new v1.3.0 architecture.
- test: updated test suites to lock in the simplified queue verification routines.
- docs: Keep single variation of `skills/resource-semaphore-v*-*` to represent the latest package, and main branch.