import importlib.metadata

try:
    __version__ = importlib.metadata.version("resource-semaphore")
except importlib.metadata.PackageNotFoundError:
    __version__ = "1.0.0"

from .asynchronous import AsyncNoopResourceSemaphore, AsyncResourceSemaphore
from .synchronous import NoopResourceSemaphore, ResourceSemaphore

__all__ = [
    "ResourceSemaphore",
    "NoopResourceSemaphore",
    "AsyncNoopResourceSemaphore",
    "AsyncResourceSemaphore",
    "__version__",
]
