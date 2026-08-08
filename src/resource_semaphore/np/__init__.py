import importlib.util

if importlib.util.find_spec("numpy") is None:
    raise ImportError(
        "The 'numpy' package is required for the 'np' subpackage. "
        "Install it with 'pip install resource-semaphore[numpy]'."
    )

from .asynchronous import AsyncNumpyResourceSemaphore
from .synchronous import NumpyResourceSemaphore

__all__ = ["NumpyResourceSemaphore", "AsyncNumpyResourceSemaphore"]
