fix: atomic event clearing & test determinism (v1.4.1)

- Fix lost-wakeup race condition on free-threaded Python builds (3.13t-3.15t) by clearing waiter events atomically under lock
- Fix small-request bypass test race condition by isolating partial capacity releases
- Overhaul test suite with deterministic queue polling handshakes, eliminating flaky sleep and timer patterns
- Re-export Ticket, SemaphoreError, BaseResourceSemaphore, and BaseAsyncResourceSemaphore at package root
- Harden get_storage() for Windows drive roots and get_cpu() with cascading container fallbacks
- Add explicit OS classifiers for Linux, Windows, and macOS to pyproject.toml
- Update documentation error table, shutdown release semantics, and sync CHANGELOG.md for 1.4.0 and 1.4.1
