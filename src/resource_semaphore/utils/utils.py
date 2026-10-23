import asyncio
import functools
import os
from collections.abc import Callable, Coroutine
from pathlib import Path
from typing import Any, ParamSpec, TypeVar

import psutil

P = ParamSpec("P")
R = TypeVar("R")


def asyncify(func: Callable[P, R]) -> Callable[P, Coroutine[Any, Any, R]]:

    @functools.wraps(func)
    async def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
        return await asyncio.to_thread(func, *args, **kwargs)

    return wrapper


def get_storage(path: str | Path | None = None) -> int:
    """
    Return free disk storage.

    Defaults to the root partition of the current working directory.
    """
    target = Path.cwd().anchor or "/" if path is None else str(path)
    return psutil.disk_usage(path=target).free


def get_memory() -> int:
    return psutil.virtual_memory().available


def get_cpu(logical: bool = False) -> int:
    """Return the number of available CPU cores.

    Args:
        logical (bool, optional): Whether to include logical (hyper-threading) cores or not. False means return physical cores only. Defaults to False.
    """
    cores = psutil.cpu_count(logical=logical)
    if cores is None and not logical:
        cores = psutil.cpu_count(logical=True)
    if cores is None:
        cores = os.cpu_count() or 1
    return cores


aget_storage = asyncify(get_storage)
aget_memory = asyncify(get_memory)
aget_cpu = asyncify(get_cpu)
