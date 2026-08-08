import asyncio
import itertools
from collections.abc import Mapping
from typing import TypeVar

from .base import BaseAsyncResourceSemaphore, SemaphoreError, Ticket

K = TypeVar("K", bound=str)


class _AsyncBaseSemaphore(BaseAsyncResourceSemaphore[K]):
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
        self._lock = asyncio.Lock()
        self._condition = asyncio.Condition(self._lock)
        self._is_shutdown = False

    async def release(self, ticket: Ticket) -> None:
        async with self._condition:
            if ticket not in self._active_tickets:
                raise ValueError("Invalid or already released ticket.")
            demands = self._active_tickets.pop(ticket)
            for name, units in demands.items():
                self._available[name] += units
            self._condition.notify_all()

    async def shutdown(self) -> None:
        async with self._condition:
            self._is_shutdown = True
            self._condition.notify_all()

    @property
    def is_shutdown(self) -> bool:
        return self._is_shutdown

    @property
    def capacity(self) -> dict[K, int]:
        return dict(self._capacity)

    @property
    def available(self) -> dict[K, int]:
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


class AsyncResourceSemaphore(_AsyncBaseSemaphore[K]):
    def __init__(self, resources: Mapping[K, int], lookahead_window: int = 1):
        super().__init__(resources)
        self.lookahead_window = lookahead_window

        # FIFO fairness
        self._seq_counter = itertools.count()
        self._queue: list[int] = []

    async def acquire(
        self, demands: Mapping[K, int], timeout: float | None = None
    ) -> Ticket:
        self._validate_demands(demands)
        seq = next(self._seq_counter)
        async with self._condition:
            self._queue.append(seq)
            try:
                deadline = (
                    None
                    if timeout is None
                    else asyncio.get_running_loop().time() + timeout
                )
                while True:
                    if self._is_shutdown:
                        raise SemaphoreError("Semaphore shut down; cannot acquire.")

                    can_acquire = self._can_acquire(demands)
                    is_eligible = True
                    if self.lookahead_window is not None:
                        try:
                            is_eligible = self._queue.index(seq) < self.lookahead_window
                        except ValueError:
                            is_eligible = False

                    if can_acquire and is_eligible:
                        break

                    remaining = None
                    if deadline is not None:
                        remaining = deadline - asyncio.get_running_loop().time()
                        if remaining <= 0:
                            raise TimeoutError(
                                f"Timed out after {timeout}s waiting to acquire {dict(demands)}."
                            )
                    try:
                        if remaining is None:
                            await self._condition.wait()
                        else:
                            await asyncio.wait_for(
                                self._condition.wait(), timeout=remaining
                            )
                    except TimeoutError:
                        continue

                for name, units in demands.items():
                    self._available[name] -= units
                ticket = Ticket()
                self._active_tickets[ticket] = dict(demands)
                return ticket
            finally:
                self._queue.remove(seq)
                self._condition.notify_all()


class AsyncGreedyResourceSemaphore(_AsyncBaseSemaphore[K]):
    """
    Async resource semaphore that does not enforce any fairness or FIFO ordering.
    Requests will acquire resources as soon as they are available, potentially
    bypassing earlier blocked requests.
    """

    async def acquire(
        self, demands: Mapping[K, int], timeout: float | None = None
    ) -> Ticket:
        self._validate_demands(demands)
        async with self._condition:
            deadline = (
                None if timeout is None else asyncio.get_running_loop().time() + timeout
            )
            while True:
                if self._is_shutdown:
                    raise SemaphoreError("Semaphore shut down; cannot acquire.")

                if self._can_acquire(demands):
                    break

                remaining = None
                if deadline is not None:
                    remaining = deadline - asyncio.get_running_loop().time()
                    if remaining <= 0:
                        raise TimeoutError(
                            f"Timed out after {timeout}s waiting to acquire {dict(demands)}."
                        )
                try:
                    if remaining is None:
                        await self._condition.wait()
                    else:
                        await asyncio.wait_for(
                            self._condition.wait(), timeout=remaining
                        )
                except TimeoutError:
                    continue

            for name, units in demands.items():
                self._available[name] -= units
            ticket = Ticket()
            self._active_tickets[ticket] = dict(demands)
            return ticket


class AsyncNoopResourceSemaphore(BaseAsyncResourceSemaphore[K]):
    """No-op resource semaphore that imposes no limits. Useful for tests."""

    async def acquire(
        self, demands: Mapping[K, int], timeout: float | None = None
    ) -> Ticket:
        return Ticket()

    async def release(self, ticket: Ticket) -> None:
        pass

    async def shutdown(self) -> None:
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
