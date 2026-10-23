# Project Roadmap & TODOs

This document tracks planned features, enhancements, and records previously completed milestones for the `resource-semaphore` project.

## Planned Features
- [x] **Resource Discovery Utilities:** Provide out-of-the-box helpers (e.g., via `psutil`) to automatically discover and read physical machine resources (Total RAM, CPU cores, DB connection limits) to initialize the semaphore dynamically.
- [x] **Tickets:** Add ticket-based resource-release mechanism.
- [x] **FIFO & Priority Queueing:** Maintain arrival-order priority among satisfiable requests while allowing smaller requests to bypass blocked heavy demands without head-of-line deadlock.
- [x] **Free-Threading Support:** Verified thread-safety and atomic event notification under free-threaded CPython (GIL-disabled) on Python 3.13t, 3.14t, and 3.15t.
- [x] **Cross-Platform System Discovery:** Hardened hardware discovery helpers for Windows root anchors and containerized CPU topology fallbacks.
- [ ] **Observability & Metrics:** Add explicit logging support and hooks for metric systems (like Prometheus counters) to allow users to trace deadlocks, view wait times, and monitor resource utilization when resources are heavily constrained.
- [x] **Timeout Support:** Add a `timeout` argument to the `.acquire()` and `.claim()` methods to allow processes to fail fast rather than blocking indefinitely when resources are exhausted.
