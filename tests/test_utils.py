from unittest.mock import patch

import pytest

from resource_semaphore.utils.utils import (
    aget_cpu,
    aget_memory,
    aget_storage,
    get_cpu,
    get_memory,
    get_storage,
)


def test_get_storage():
    with patch("psutil.disk_usage") as mock_disk:
        mock_disk.return_value.free = 1000
        assert get_storage() == 1000
        assert get_storage("/tmp") == 1000


def test_get_memory():
    with patch("psutil.virtual_memory") as mock_mem:
        mock_mem.return_value.available = 2000
        assert get_memory() == 2000


def test_get_cpu():
    with patch("psutil.cpu_count") as mock_cpu:
        mock_cpu.return_value = 4
        assert get_cpu() == 4
        mock_cpu.assert_called_with(logical=False)


@pytest.mark.asyncio
async def test_aget_storage():
    with patch("psutil.disk_usage") as mock_disk:
        mock_disk.return_value.free = 1000
        assert await aget_storage() == 1000


@pytest.mark.asyncio
async def test_aget_memory():
    with patch("psutil.virtual_memory") as mock_mem:
        mock_mem.return_value.available = 2000
        assert await aget_memory() == 2000


@pytest.mark.asyncio
async def test_aget_cpu():
    with patch("psutil.cpu_count") as mock_cpu:
        mock_cpu.return_value = 4
        assert await aget_cpu() == 4
        mock_cpu.assert_called_with(logical=False)


def test_utils_import_error():
    import importlib

    import resource_semaphore.utils

    with patch.dict("sys.modules", {"psutil": None}):
        with pytest.raises(RuntimeError, match="`utils` subpackage isn't available"):
            importlib.reload(resource_semaphore.utils)

    importlib.reload(resource_semaphore.utils)


def test_utils_other_error():
    import builtins
    import importlib

    import resource_semaphore.utils

    orig_import = builtins.__import__

    def mock_import(name, *args, **kwargs):
        if name == "psutil":
            raise ValueError("Something went terribly wrong")
        return orig_import(name, *args, **kwargs)

    with patch("builtins.__import__", side_effect=mock_import):
        with pytest.raises(ValueError, match="Something went terribly wrong"):
            importlib.reload(resource_semaphore.utils)

    importlib.reload(resource_semaphore.utils)
