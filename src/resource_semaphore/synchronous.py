import itertools
import threading
import time
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Generic, TypeVar

from .base import BaseResourceSemaphore, SemaphoreError, Ticket

K = TypeVar("K", bound=str)


@dataclass
class _SyncWaiter(Generic[K]):
    seq: int
    demands: dict[K, int]
    event: threading.Event


class _SyncBaseSemaphore(BaseResourceSemaphore[K]):
    def __init__(self, resources: Mapping[K, int]):
        if not resources:
            raise ValueError("Semaphore requires at least one resource.")
        for name, cap in resources.items():
            self._check_int(name, cap, "capacity")
            if cap <= 0:
                raise ValueError(
                    f"Resource '{name}' capacity must be positive, got {cap}."
                )
        self._capacity: dict[K, int] = dict(resources)
        self._available: dict[K, int] = dict(resources)
        self._active_tickets: dict[Ticket, dict[K, int]] = {}
        self._lock = threading.Lock()
        self._waiters: list[_SyncWaiter] = []
        self._is_shutdown = False

    def _notify_first_eligible(self) -> None:
        """Wake the first (earliest-arrived) waiter whose demands fit.

        Only ever wakes ONE waiter -- never notify_all(). Waking a single
        specific candidate avoids the thundering herd where every blocked
        thread wakes up, fights over the lock, and finds it still can't
        proceed. If a release frees enough for more than one waiter, the
        winner's own successful acquire() re-runs this in its `finally`,
        so the next eligible waiter gets woken in turn.
        """
        for waiter in self._waiters:
            if self._can_acquire(waiter.demands):
                waiter.event.set()
                return

    def _claim_locked(self, demands: Mapping[K, int]) -> Ticket:
        """Deduct `demands` and mint a ticket. Caller must hold self._lock."""
        for name, units in demands.items():
            self._available[name] -= units
        ticket = Ticket()
        self._active_tickets[ticket] = dict(demands)
        return ticket

    def release(self, ticket: Ticket):
        with self._lock:
            if ticket not in self._active_tickets:
                raise ValueError("Invalid or already released ticket.")
            demands = self._active_tickets.pop(ticket)
            for name, units in demands.items():
                self._available[name] += units
            self._notify_first_eligible()

    def shutdown(self) -> None:
        with self._lock:
            self._is_shutdown = True
            # Deliberate exception to the "wake exactly one" rule above:
            # shutdown is a one-time terminal event, every waiter must
            # observe it, and the post-wake work is just "raise", so
            # there's no wasted recomputation to guard against here.
            for waiter in self._waiters:
                waiter.event.set()

    @property
    def is_shutdown(self) -> bool:
        with self._lock:
            return self._is_shutdown

    @property
    def capacity(self) -> dict[K, int]:
        return dict(self._capacity)

    @property
    def available(self) -> dict[K, int]:
        with self._lock:
            return dict(self._available)

    def _validate_demands(self, demands: Mapping[K, int]) -> None:
        if not demands:
            raise ValueError("acquire() requires at least one resource demand.")
        for name, units in demands.items():
            self._check_int(name, units, "demand")
            if name not in self._capacity:
                raise ValueError(f"Unknown resource: {name}")
            if units <= 0:
                raise ValueError(
                    f"Resource '{name}' units must be positive, got {units}."
                )
            if units > self._capacity[name]:
                raise ValueError(
                    f"Demand for '{name}' ({units}) exceeds capacity ({self._capacity[name]})."
                )

    def _can_acquire(self, demands: Mapping[K, int]) -> bool:
        return all(self._available[n] >= u for n, u in demands.items())

    @staticmethod
    def _check_int(name: K, value: object, label: str) -> None:
        if isinstance(value, bool) or not isinstance(value, int):
            raise TypeError(
                f"Resource '{name}' {label} must be an integer, got {type(value).__name__}."
            )


class ResourceSemaphore(_SyncBaseSemaphore[K]):
    """
    Multi-resource counting semaphore with queue fairness.

    A waiter is granted as soon as its demand fits AND no earlier-arrived
    waiter could *also* currently be satisfied. This is deliberately not
    strict head-of-line blocking: a later, smaller request can jump an
    earlier, larger one that doesn't fit yet, so one big request can't
    stall everyone behind it. Among requests that are simultaneously
    satisfiable, the earliest arrival always wins.
    """

    def __init__(self, resources: Mapping[K, int]):
        super().__init__(resources)
        self._seq_counter = itertools.count()

    def _is_first_eligible(self, my_seq: int) -> bool:
        """True iff no earlier-arrived waiter could currently acquire.

        `self._waiters` is already in arrival order (append-only at the
        tail; removals preserve the relative order of what's left), so
        this is a single O(n) pass -- no separate seq queue needed, and
        no need to search `self._waiters` for the waiter matching each
        seq the way the previous implementation did.
        """
        for waiter in self._waiters:
            if waiter.seq == my_seq:
                return True
            if self._can_acquire(waiter.demands):
                return False
        return True

    def acquire(self, demands: Mapping[K, int], timeout: float | None = None) -> Ticket:
        self._validate_demands(demands)

        # Fast path: nobody's ahead of us
        with self._lock:
            if self._is_shutdown:
                raise SemaphoreError("Semaphore shut down; cannot acquire.")
            if not self._waiters and self._can_acquire(demands):
                return self._claim_locked(demands)

        seq = next(self._seq_counter)
        waiter = _SyncWaiter(seq=seq, demands=dict(demands), event=threading.Event())

        with self._lock:
            self._waiters.append(waiter)

        try:
            deadline = None if timeout is None else time.monotonic() + timeout
            while True:
                with self._lock:
                    if self._is_shutdown:
                        raise SemaphoreError("Semaphore shut down; cannot acquire.")

                    if self._can_acquire(demands) and self._is_first_eligible(seq):
                        return self._claim_locked(demands)

                remaining = None
                if deadline is not None:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise TimeoutError(
                            f"Timed out after {timeout}s waiting to acquire {dict(demands)}."
                        )
                waiter.event.wait(timeout=remaining)
                waiter.event.clear()
        finally:
            with self._lock:
                self._waiters.remove(waiter)
                self._notify_first_eligible()


class GreedyResourceSemaphore(_SyncBaseSemaphore[K]):
    """
    Resource semaphore that does not enforce any fairness or FIFO ordering.
    Requests will acquire resources as soon as they are available, potentially
    bypassing earlier blocked requests.
    """

    def acquire(self, demands: Mapping[K, int], timeout: float | None = None) -> Ticket:
        self._validate_demands(demands)
        with self._lock:
            if self._is_shutdown:
                raise SemaphoreError("Semaphore shut down; cannot acquire.")
            if self._can_acquire(demands):
                return self._claim_locked(demands)

        waiter = _SyncWaiter(seq=0, demands=dict(demands), event=threading.Event())
        with self._lock:
            self._waiters.append(waiter)
        try:
            deadline = None if timeout is None else time.monotonic() + timeout
            while True:
                with self._lock:
                    if self._is_shutdown:
                        raise SemaphoreError("Semaphore shut down; cannot acquire.")
                    if self._can_acquire(demands):
                        return self._claim_locked(demands)
                remaining = None
                if deadline is not None:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0:
                        raise TimeoutError(
                            f"Timed out after {timeout}s waiting to acquire {dict(demands)}."
                        )
                waiter.event.wait(timeout=remaining)
                waiter.event.clear()
        finally:
            with self._lock:
                self._waiters.remove(waiter)
                self._notify_first_eligible()


class NoopResourceSemaphore(BaseResourceSemaphore[K]):
    """No-op resource semaphore that imposes no limits. Useful for tests."""

    def acquire(self, demands: Mapping[K, int], timeout: float | None = None) -> Ticket:
        return Ticket()

    def release(self, ticket: Ticket) -> None:
        pass

    def shutdown(self) -> None:
        pass

    @property
    def is_shutdown(self) -> bool:
        return False

    @property
    def capacity(self) -> dict[K, int]:
        return {}

    @property
    def available(self) -> dict[K, int]:
        return {}
