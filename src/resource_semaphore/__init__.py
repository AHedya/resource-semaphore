import importlib.metadata

try:
    __version__ = importlib.metadata.version("resource-semaphore")
except importlib.metadata.PackageNotFoundError:
    __version__ = "1.0.0"

from .asynchronous import (
    AsyncGreedyResourceSemaphore,
    AsyncNoopResourceSemaphore,
    AsyncResourceSemaphore,
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
    "__version__",
]
