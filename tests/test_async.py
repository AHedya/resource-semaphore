import asyncio
from typing import Literal

import pytest

from resource_semaphore.asynchronous import (
    AsyncNoopResourceSemaphore,
    AsyncResourceSemaphore,
)
from resource_semaphore.base import SemaphoreError, Ticket
from resource_semaphore.np import AsyncNumpyResourceSemaphore


@pytest.fixture(params=[AsyncResourceSemaphore, AsyncNumpyResourceSemaphore])
def async_semaphore_cls(request):
    return request.param


class TestAsyncResourceSemaphoreInit:
    async def test_basic_creation(self, async_semaphore_cls):
        rs = async_semaphore_cls(resources={"cpu": 1, "RAM_MB": 2048})
        assert rs.capacity == {"cpu": 1, "RAM_MB": 2048}
        assert rs.available == {"cpu": 1, "RAM_MB": 2048}

    async def test_empty_resources_raises(self, async_semaphore_cls):
        with pytest.raises(ValueError, match="at least one resource"):
            async_semaphore_cls(resources={})

    async def test_zero_capacity_raises(self, async_semaphore_cls):
        with pytest.raises(ValueError, match="must be positive"):
            async_semaphore_cls(resources={"cpu": 0})

    async def test_negative_capacity_raises(self, async_semaphore_cls):
        with pytest.raises(ValueError, match="must be positive"):
            async_semaphore_cls(resources={"cpu": -1})


class TestAcquireRelease:
    async def test_release_invalid_ticket_raises(self, async_semaphore_cls):
        rs = async_semaphore_cls(resources={"cpu": 1})

        with pytest.raises(ValueError, match="Invalid or already released ticket"):
            await rs.release(Ticket())

    async def test_acquire_and_release(self, async_semaphore_cls):
        rs = async_semaphore_cls(resources={"cpu": 2})
        ticket = await rs.acquire({"cpu": 1})
        assert rs.available == {"cpu": 1}
        await rs.release(ticket)
        assert rs.available == {"cpu": 2}

    async def test_acquire_full_capacity(self, async_semaphore_cls):
        rs = async_semaphore_cls(resources={"cpu": 1})
        ticket = await rs.acquire({"cpu": 1})
        assert rs.available == {"cpu": 0}
        await rs.release(ticket)
        assert rs.available == {"cpu": 1}

    async def test_multi_resource_acquire(self, async_semaphore_cls):
        rs = async_semaphore_cls(resources={"cpu": 2, "RAM_MB": 2048})
        ticket = await rs.acquire({"cpu": 1, "RAM_MB": 500})
        assert rs.available == {"cpu": 1, "RAM_MB": 1548}
        await rs.release(ticket)
        assert rs.available == {"cpu": 2, "RAM_MB": 2048}

    async def test_acquire_unknown_resource_raises(self, async_semaphore_cls):
        rs = async_semaphore_cls(resources={"cpu": 1})
        with pytest.raises(ValueError, match="Unknown resource"):
            await rs.acquire({"db_conn": 1})

    async def test_acquire_zero_demand_raises(self, async_semaphore_cls):
        rs = async_semaphore_cls(resources={"cpu": 1})
        with pytest.raises(ValueError, match="must be positive"):
            await rs.acquire({"cpu": 0})

    async def test_acquire_negative_demand_raises(self, async_semaphore_cls):
        rs = async_semaphore_cls(resources={"cpu": 1})
        with pytest.raises(ValueError, match="must be positive"):
            await rs.acquire({"cpu": -1})

    async def test_acquire_empty_demands_raises(self, async_semaphore_cls):
        rs = async_semaphore_cls(resources={"cpu": 1})
        with pytest.raises(ValueError, match="at least one resource demand"):
            await rs.acquire({})

    async def test_acquire_exceeding_cap(self, async_semaphore_cls):
        rs = async_semaphore_cls(resources={"cpu": 3})
        with pytest.raises(ValueError):
            await rs.acquire({"cpu": 5})

    async def test_fractional_units_raises(self, async_semaphore_cls):
        rs = async_semaphore_cls(resources={"RAM_MB": 2048})
        with pytest.raises(TypeError, match="must be an integer"):
            await rs.acquire({"RAM_MB": 500.5})  # type: ignore [bad-assignment]


class TestAsyncClaimContextManager:
    async def test_claim_success(self, async_semaphore_cls):
        rs = async_semaphore_cls(resources={"cpu": 2})
        async with rs.claim({"cpu": 1}):
            assert rs.available == {"cpu": 1}
        assert rs.available == {"cpu": 2}

    async def test_claim_exception_releases_resources(self, async_semaphore_cls):
        rs = async_semaphore_cls(resources={"cpu": 2})
        try:
            async with rs.claim({"cpu": 1}):
                assert rs.available == {"cpu": 1}
                raise RuntimeError("Something went wrong")
        except RuntimeError:
            pass
        assert rs.available == {"cpu": 2}

    async def test_claim_blocks_if_unavailable(self, async_semaphore_cls):
        rs = async_semaphore_cls(resources={"cpu": 1})
        ticket = await rs.acquire({"cpu": 1})

        waiting_event = asyncio.Event()
        acquired = asyncio.Event()
        done = asyncio.Event()

        async def blocked_claim():
            waiting_event.set()
            async with rs.claim({"cpu": 1}):
                acquired.set()
                await asyncio.wait_for(done.wait(), timeout=5)

        t = asyncio.create_task(blocked_claim())

        await asyncio.wait_for(waiting_event.wait(), timeout=2)
        await asyncio.sleep(0.05)
        assert not acquired.is_set()

        await rs.release(ticket)
        await asyncio.wait_for(acquired.wait(), timeout=2)
        done.set()
        await asyncio.wait_for(t, timeout=2)


class TestBlockingAcquire:
    async def test_acquire_blocks_until_available(self, async_semaphore_cls):
        rs = async_semaphore_cls(resources={"cpu": 1})
        ticket = await rs.acquire({"cpu": 1})

        waiting_event = asyncio.Event()
        acquired = asyncio.Event()
        done = asyncio.Event()

        async def blocked_acquire():
            waiting_event.set()
            _ticket = await rs.acquire({"cpu": 1})
            acquired.set()
            await asyncio.wait_for(done.wait(), timeout=5)

        t = asyncio.create_task(blocked_acquire())

        await asyncio.wait_for(waiting_event.wait(), timeout=2)
        await asyncio.sleep(0.05)
        assert not acquired.is_set()

        await rs.release(ticket)
        await asyncio.wait_for(acquired.wait(), timeout=2)
        done.set()
        await asyncio.wait_for(t, timeout=2)

    async def test_atomic_multi_resource_acquire(self, async_semaphore_cls):
        rs = async_semaphore_cls(resources={"cpu": 1, "RAM_MB": 1000})
        ticket = await rs.acquire({"cpu": 1})

        waiting_event = asyncio.Event()
        acquired = asyncio.Event()
        release_event = asyncio.Event()

        async def blocked_acquire():
            waiting_event.set()
            _ticket = await rs.acquire({"cpu": 1, "RAM_MB": 500})
            acquired.set()
            await asyncio.wait_for(release_event.wait(), timeout=5)

        t = asyncio.create_task(blocked_acquire())

        await asyncio.wait_for(waiting_event.wait(), timeout=2)
        await asyncio.sleep(0.05)
        assert not acquired.is_set()

        await rs.release(ticket)
        await asyncio.wait_for(acquired.wait(), timeout=2)
        assert rs.available == {"cpu": 0, "RAM_MB": 500}
        release_event.set()
        await asyncio.wait_for(t, timeout=2)

    async def test_multiple_waiters_woken(self, async_semaphore_cls):
        rs = async_semaphore_cls(resources={"cpu": 2})
        ticket = await rs.acquire({"cpu": 2})

        waiting_events = [asyncio.Event() for _ in range(2)]
        events = [asyncio.Event() for _ in range(2)]
        release_events = [asyncio.Event() for _ in range(2)]

        async def waiter(idx):
            waiting_events[idx].set()
            _ticket = await rs.acquire({"cpu": 1})
            events[idx].set()
            await asyncio.wait_for(release_events[idx].wait(), timeout=5)

        tasks = [asyncio.create_task(waiter(i)) for i in range(2)]

        for we in waiting_events:
            await asyncio.wait_for(we.wait(), timeout=2)
        await asyncio.sleep(0.05)
        assert not any(e.is_set() for e in events)

        await rs.release(ticket)

        for e in events:
            await asyncio.wait_for(e.wait(), timeout=2)

        for re in release_events:
            re.set()

        await asyncio.gather(*tasks)


class TestShutdown:
    async def test_shutdown_wakes_blocked_acquire(self, async_semaphore_cls):
        rs = async_semaphore_cls(resources={"cpu": 1})
        _ticket = await rs.acquire({"cpu": 1})

        waiting_event = asyncio.Event()
        errors = []

        async def blocked_acquire():
            waiting_event.set()
            try:
                _ticket = await rs.acquire({"cpu": 1})
            except SemaphoreError as e:
                errors.append(e)

        t = asyncio.create_task(blocked_acquire())

        await asyncio.wait_for(waiting_event.wait(), timeout=2)
        await asyncio.sleep(0.05)
        await rs.shutdown()
        await asyncio.wait_for(t, timeout=2)

        assert len(errors) == 1
        assert "shut down" in str(errors[0])

    async def test_acquire_after_shutdown_raises(self, async_semaphore_cls):
        rs = async_semaphore_cls(resources={"cpu": 1})
        await rs.shutdown()
        with pytest.raises(SemaphoreError, match="shut down"):
            await rs.acquire({"cpu": 1})

    async def test_shutdown_idempotent(self, async_semaphore_cls):
        rs = async_semaphore_cls(resources={"cpu": 1})
        await rs.shutdown()
        await rs.shutdown()
        assert rs.is_shutdown


class TestProperties:
    async def test_available_snapshot(self, async_semaphore_cls):
        rs = async_semaphore_cls(resources={"cpu": 2})
        snap = rs.available
        _ticket = await rs.acquire({"cpu": 1})
        assert snap == {"cpu": 2}
        assert rs.available == {"cpu": 1}

    async def test_capacity_snapshot(self, async_semaphore_cls):
        rs = async_semaphore_cls(resources={"cpu": 2})
        snap = rs.capacity
        assert snap == {"cpu": 2}

    async def test_generic_type(self, async_semaphore_cls):

        _rs = async_semaphore_cls[Literal["cpu", "RAM_MB"]](resources={"cpu": 2})


class TestTimeout:
    async def test_acquire_success_within_timeout(self, async_semaphore_cls):
        rs = async_semaphore_cls({"cpu": 1})
        ticket1 = await rs.acquire({"cpu": 1})

        async def delayed_release():
            await asyncio.sleep(0.1)
            await rs.release(ticket1)

        asyncio.create_task(delayed_release())

        ticket2 = await rs.acquire({"cpu": 1}, timeout=1.0)
        assert rs.available == {"cpu": 0}
        await rs.release(ticket2)

    async def test_acquire_timeout_raises(self, async_semaphore_cls):
        rs = async_semaphore_cls({"cpu": 1})
        await rs.acquire({"cpu": 1})

        with pytest.raises(TimeoutError, match="Timed out"):
            await rs.acquire({"cpu": 1}, timeout=0.1)

    async def test_claim_timeout_raises(self, async_semaphore_cls):
        rs = async_semaphore_cls({"cpu": 1})
        await rs.acquire({"cpu": 1})

        with pytest.raises(TimeoutError, match="Timed out"):
            async with rs.claim({"cpu": 1}, timeout=0.1):
                pass


async def test_async_noop_semaphore():
    rs = AsyncNoopResourceSemaphore()
    assert rs.capacity == {}
    assert rs.available == {}
    assert rs.is_shutdown is False

    ticket = await rs.acquire({"cpu": 1})
    assert isinstance(ticket, Ticket)

    await rs.release(ticket)

    await rs.shutdown()

    assert rs.is_shutdown is False  # type: ignore
