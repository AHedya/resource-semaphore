import itertools
import threading
import time
from collections.abc import Mapping
from typing import TypeVar

from .base import BaseResourceSemaphore, SemaphoreError, Ticket

K = TypeVar("K", bound=str)


class ResourceSemaphore(BaseResourceSemaphore[K]):
    """
    Multi-resource counting semaphore.
    """

    def __init__(self, resources: Mapping[K, int]):
        if not resources:
            raise ValueError("ResourceSemaphore requires at least one resource.")
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
        self._condition = threading.Condition(self._lock)
        self._is_shutdown = False

        # FIFO fairness
        self._seq_counter = itertools.count()
        self._queue: list[int] = []

    def acquire(self, demands: Mapping[K, int], timeout: float | None = None) -> Ticket:
        self._validate_demands(demands)

        seq = next(self._seq_counter)
        with self._condition:
            self._queue.append(seq)
            try:
                deadline = None if timeout is None else time.monotonic() + timeout
                while not (self._queue[0] == seq and self._can_acquire(demands)):
                    if self._is_shutdown:
                        raise SemaphoreError("Semaphore shut down; cannot acquire.")
                    remaining = None
                    if deadline is not None:
                        remaining = deadline - time.monotonic()
                        if remaining <= 0:
                            raise TimeoutError(
                                f"Timed out after {timeout}s waiting to acquire {dict(demands)}."
                            )
                    if not self._condition.wait(timeout=remaining):
                        continue
                if self._is_shutdown:
                    raise SemaphoreError("Semaphore shut down; cannot acquire.")

                for name, units in demands.items():
                    self._available[name] -= units
                ticket = Ticket()
                self._active_tickets[ticket] = dict(demands)
                return ticket
            finally:
                self._queue.remove(seq)
                self._condition.notify_all()

    def release(self, ticket: Ticket):
        with self._condition:
            if ticket not in self._active_tickets:
                raise ValueError("Invalid or already released ticket.")
            demands = self._active_tickets.pop(ticket)
            for name, units in demands.items():
                self._available[name] += units
            self._condition.notify_all()

    def shutdown(self) -> None:
        with self._condition:
            self._is_shutdown = True
            self._condition.notify_all()

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
