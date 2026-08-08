try:
    import psutil  # noqa: F401
except ImportError:
    raise RuntimeError(
        "`utils` subpackage isn't available. install `utils` extension: `pip install resource-semaphore[utils] `"
    )
except Exception:
    raise

from .utils import aget_cpu, aget_memory, aget_storage, get_cpu, get_memory, get_storage

__all__ = [
    "get_cpu",
    "aget_cpu",
    "get_storage",
    "get_memory",
    "aget_memory",
    "aget_storage",
]
