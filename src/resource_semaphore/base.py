import uuid
from abc import ABC, abstractmethod
from collections.abc import Mapping
from contextlib import asynccontextmanager, contextmanager
from dataclasses import dataclass, field
from typing import Generic, TypeVar

K = TypeVar("K", bound=str)


class SemaphoreError(Exception):
    """Raised when resource acquisition fails (e.g., semaphore is shut down)."""


@dataclass(frozen=True, slots=True)
class Ticket:
    """An opaque ticket representing acquired resources."""

    id: uuid.UUID = field(default_factory=uuid.uuid4)

    def __repr__(self) -> str:
        return f"<Ticket {self.id.hex[:8]}>"


class _BaseSemaphore(ABC, Generic[K]):
    @property
    @abstractmethod
    def is_shutdown(self) -> bool: ...

    @property
    @abstractmethod
    def capacity(self) -> dict[K, int]: ...

    @property
    @abstractmethod
    def available(self) -> dict[K, int]: ...


class BaseResourceSemaphore(_BaseSemaphore[K]):
    """Interface for sync resource semaphore."""

    @abstractmethod
    def acquire(
        self, demands: Mapping[K, int], timeout: float | None = None
    ) -> Ticket: ...

    @abstractmethod
    def release(self, ticket: Ticket) -> None: ...

    @contextmanager
    def claim(self, demands: Mapping[K, int], timeout: float | None = None):
        """Context manager: acquire on enter, release on exit."""
        ticket = self.acquire(demands, timeout=timeout)
        try:
            yield ticket
        finally:
            self.release(ticket)

    @abstractmethod
    def shutdown(self) -> None: ...


class BaseAsyncResourceSemaphore(_BaseSemaphore[K]):
    """Interface for async resource semaphore."""

    @abstractmethod
    async def acquire(
        self, demands: Mapping[K, int], timeout: float | None = None
    ) -> Ticket: ...

    @abstractmethod
    async def release(self, ticket: Ticket) -> None: ...

    @asynccontextmanager
    async def claim(self, demands: Mapping[K, int], timeout: float | None = None):
        """Async context manager: acquire on enter, release on exit."""
        ticket = await self.acquire(demands, timeout=timeout)
        try:
            yield ticket
        finally:
            await self.release(ticket)

    @abstractmethod
    async def shutdown(self) -> None: ...
