# Project Roadmap & TODOs

This document tracks planned features, enhancements, and records previously completed milestones for the `resource-semaphore` project.

## Planned Features

- [x] **NumPy Vectorization:** Implement matrix-based vectorization for fast Python-time queue scanning (`NumpyResourceSemaphore`).
- [x] **Resource Discovery Utilities:** Provide out-of-the-box helpers (e.g., via `psutil`) to automatically discover and read physical machine resources (Total RAM, CPU cores, DB connection limits) to initialize the semaphore dynamically.
- [x] **Tickets:** Add ticket-based resource-release mechanism.
- [x] **FIFO**: Provide an order-maintaining mechanism. Keep the claim order, and notify on order
- [ ] **Observability & Metrics:** Add explicit logging support and hooks for metric systems (like Prometheus counters) to allow users to trace deadlocks, view wait times, and monitor resource utilization when resources are heavily constrained.
- [x] **Timeout Support:** Add a `timeout` argument to the `.acquire()` and `.claim()` methods to allow processes to fail fast rather than blocking indefinitely when resources are exhausted.
