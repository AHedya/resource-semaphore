import importlib.metadata

try:
    __version__ = importlib.metadata.version("resource-semaphore")
except importlib.metadata.PackageNotFoundError:
    __version__ = "0.0.0+dev0"

from .asynchronous import (
    AsyncGreedyResourceSemaphore,
    AsyncNoopResourceSemaphore,
    AsyncResourceSemaphore,
)
from .base import (
    BaseAsyncResourceSemaphore,
    BaseResourceSemaphore,
    SemaphoreError,
    Ticket,
)
from .synchronous import (
    GreedyResourceSemaphore,
    NoopResourceSemaphore,
    ResourceSemaphore,
)

__all__ = [
    "ResourceSemaphore",
    "GreedyResourceSemaphore",
    "NoopResourceSemaphore",
    "AsyncNoopResourceSemaphore",
    "AsyncResourceSemaphore",
    "AsyncGreedyResourceSemaphore",
    "BaseResourceSemaphore",
    "BaseAsyncResourceSemaphore",
    "SemaphoreError",
    "Ticket",
    "__version__",
]
