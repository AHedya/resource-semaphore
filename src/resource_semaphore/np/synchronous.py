import itertools
import threading
import time
from collections.abc import Mapping
from dataclasses import dataclass
from typing import TypeVar

import numpy as np

from ..base import BaseResourceSemaphore, SemaphoreError, Ticket

K = TypeVar("K", bound=str)


@dataclass(slots=True, frozen=True)
class _NpSyncWaiter:
    seq: int
    demands_arr: np.ndarray
    event: threading.Event


class NumpyResourceSemaphore(BaseResourceSemaphore[K]):
    """
    Numpy-backed multi-resource semaphore.
    """

    def __init__(self, resources: Mapping[K, int]):
        if not resources:
            raise ValueError("Semaphore requires at least one resource.")

        self._keys = list(resources.keys())
        self._key_to_idx = {k: i for i, k in enumerate(self._keys)}

        caps = []
        for name, cap in resources.items():
            self._check_int(name, cap, "capacity")
            if cap <= 0:
                raise ValueError(
                    f"Resource '{name}' capacity must be positive, got {cap}."
                )
            caps.append(cap)

        self._capacity_arr = np.array(caps, dtype=np.int64)
        self._available_arr = self._capacity_arr.copy()

        self._active_tickets: dict[Ticket, np.ndarray] = {}
        self._lock = threading.Lock()

        self._waiters: list[_NpSyncWaiter] = []
        self._is_shutdown = False

        self._seq_counter = itertools.count()

    def _dict_to_arr(self, demands: Mapping[K, int]) -> np.ndarray:
        if not demands:
            raise ValueError("acquire() requires at least one resource demand.")
        arr = np.zeros(len(self._keys), dtype=np.int64)
        for name, units in demands.items():
            if name not in self._key_to_idx:
                raise ValueError(f"Unknown resource: {name}")
            self._check_int(name, units, "demand")
            if units <= 0:
                raise ValueError(
                    f"Resource '{name}' units must be positive, got {units}."
                )
            if units > self._capacity_arr[self._key_to_idx[name]]:
                raise ValueError(f"Demand for '{name}' ({units}) exceeds capacity.")
            arr[self._key_to_idx[name]] = units
        return arr

    def _notify_first_eligible(self) -> None:
        """Wake the single earliest-arrived waiter whose demand now fits."""
        if not self._waiters:
            return

        demands_matrix = np.vstack([w.demands_arr for w in self._waiters])
        can_satisfy = np.all(demands_matrix <= self._available_arr, axis=1)

        if np.any(can_satisfy):
            first_eligible_idx = int(np.argmax(can_satisfy))
            self._waiters[first_eligible_idx].event.set()

    def _is_first_eligible(self, seq: int) -> bool:
        """True iff no earlier-arrived waiter could currently acquire."""
        if not self._waiters:
            return True

        idx = next((i for i, w in enumerate(self._waiters) if w.seq == seq), None)
        if not idx:
            return True

        demands_matrix = np.vstack([w.demands_arr for w in self._waiters[:idx]])
        can_satisfy = np.all(demands_matrix <= self._available_arr, axis=1)
        return not bool(np.any(can_satisfy))

    def _claim_locked(self, demands_arr: np.ndarray) -> Ticket:
        """Deduct `demands_arr` and mint a ticket. Caller must hold self._lock."""
        self._available_arr -= demands_arr
        ticket = Ticket()
        self._active_tickets[ticket] = demands_arr
        return ticket

    def acquire(self, demands: Mapping[K, int], timeout: float | None = None) -> Ticket:
        demands_arr = self._dict_to_arr(demands)

        # Fast path
        with self._lock:
            if self._is_shutdown:
                raise SemaphoreError("Semaphore shut down; cannot acquire.")
            if not self._waiters and bool(np.all(self._available_arr >= demands_arr)):
                return self._claim_locked(demands_arr)

        seq = next(self._seq_counter)
        waiter = _NpSyncWaiter(
            seq=seq, demands_arr=demands_arr, event=threading.Event()
        )

        with self._lock:
            self._waiters.append(waiter)

        try:
            deadline = None if timeout is None else time.monotonic() + timeout
            while True:
                with self._lock:
                    if self._is_shutdown:
                        raise SemaphoreError("Semaphore shut down; cannot acquire.")

                    if bool(
                        np.all(self._available_arr >= demands_arr)
                    ) and self._is_first_eligible(seq):
                        return self._claim_locked(demands_arr)

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

    def release(self, ticket: Ticket) -> None:
        with self._lock:
            if ticket not in self._active_tickets:
                raise ValueError("Invalid or already released ticket.")
            demands_arr = self._active_tickets.pop(ticket)
            self._available_arr += demands_arr
            self._notify_first_eligible()

    def shutdown(self) -> None:
        with self._lock:
            self._is_shutdown = True
            for waiter in self._waiters:
                waiter.event.set()

    @property
    def is_shutdown(self) -> bool:
        with self._lock:
            return self._is_shutdown

    @property
    def capacity(self) -> dict[K, int]:
        return {k: int(self._capacity_arr[i]) for k, i in self._key_to_idx.items()}

    @property
    def available(self) -> dict[K, int]:
        with self._lock:
            return {k: int(self._available_arr[i]) for k, i in self._key_to_idx.items()}

    @staticmethod
    def _check_int(name: K, value: object, label: str) -> None:
        if isinstance(value, bool) or not isinstance(value, int):
            raise TypeError(
                f"Resource '{name}' {label} must be an integer, got {type(value).__name__}."
            )
