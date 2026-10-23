import asyncio
from typing import Literal

import pytest

from resource_semaphore.asynchronous import (
    AsyncGreedyResourceSemaphore,
    AsyncNoopResourceSemaphore,
    AsyncResourceSemaphore,
    _AsyncWaiter,
)
from resource_semaphore.base import SemaphoreError, Ticket


@pytest.fixture(params=[AsyncResourceSemaphore, AsyncGreedyResourceSemaphore])
def async_semaphore_cls(request):
    return request.param


async def _wait_for_waiters(rs, count: int, timeout: float = 5.0) -> None:
    deadline = asyncio.get_running_loop().time() + timeout
    while asyncio.get_running_loop().time() < deadline:
        async with rs._lock:
            if len(rs._waiters) >= count:
                return
        await asyncio.sleep(0.001)
    raise TimeoutError(f"Waiters count did not reach {count} within {timeout}s")


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

        acquired = asyncio.Event()
        done = asyncio.Event()

        async def blocked_claim():
            async with rs.claim({"cpu": 1}):
                acquired.set()
                await asyncio.wait_for(done.wait(), timeout=5)

        t = asyncio.create_task(blocked_claim())

        await _wait_for_waiters(rs, 1)
        assert not acquired.is_set()

        await rs.release(ticket)
        await asyncio.wait_for(acquired.wait(), timeout=5)
        done.set()
        await asyncio.wait_for(t, timeout=2)


class TestBlockingAcquire:
    async def test_acquire_blocks_until_available(self, async_semaphore_cls):
        rs = async_semaphore_cls(resources={"cpu": 1})
        ticket = await rs.acquire({"cpu": 1})

        acquired = asyncio.Event()
        done = asyncio.Event()

        async def blocked_acquire():
            _ticket = await rs.acquire({"cpu": 1})
            acquired.set()
            await asyncio.wait_for(done.wait(), timeout=5)

        t = asyncio.create_task(blocked_acquire())

        await _wait_for_waiters(rs, 1)
        assert not acquired.is_set()

        await rs.release(ticket)
        await asyncio.wait_for(acquired.wait(), timeout=5)
        done.set()
        await asyncio.wait_for(t, timeout=2)

    async def test_atomic_multi_resource_acquire(self, async_semaphore_cls):
        rs = async_semaphore_cls(resources={"cpu": 1, "RAM_MB": 1000})
        ticket = await rs.acquire({"cpu": 1})

        acquired = asyncio.Event()
        release_event = asyncio.Event()

        async def blocked_acquire():
            _ticket = await rs.acquire({"cpu": 1, "RAM_MB": 500})
            acquired.set()
            await asyncio.wait_for(release_event.wait(), timeout=5)

        t = asyncio.create_task(blocked_acquire())

        await _wait_for_waiters(rs, 1)
        assert not acquired.is_set()

        await rs.release(ticket)
        await asyncio.wait_for(acquired.wait(), timeout=5)
        assert rs.available == {"cpu": 0, "RAM_MB": 500}
        release_event.set()
        await asyncio.wait_for(t, timeout=2)

    async def test_multiple_waiters_woken(self, async_semaphore_cls):
        rs = async_semaphore_cls(resources={"cpu": 2})
        ticket = await rs.acquire({"cpu": 2})

        events = [asyncio.Event() for _ in range(2)]
        release_events = [asyncio.Event() for _ in range(2)]

        async def waiter(idx):
            _ticket = await rs.acquire({"cpu": 1})
            events[idx].set()
            await asyncio.wait_for(release_events[idx].wait(), timeout=5)

        tasks = [asyncio.create_task(waiter(i)) for i in range(2)]

        await _wait_for_waiters(rs, 2)
        assert not any(e.is_set() for e in events)

        await rs.release(ticket)

        for e in events:
            await asyncio.wait_for(e.wait(), timeout=5)

        for re in release_events:
            re.set()

        await asyncio.gather(*tasks)

    async def test_first_eligible_priority(self):

        rs = AsyncResourceSemaphore(resources={"cpu": 2})
        t = await rs.acquire({"cpu": 2})

        w1 = _AsyncWaiter(seq=0, demands={"cpu": 1}, event=asyncio.Event())
        w2 = _AsyncWaiter(seq=1, demands={"cpu": 1}, event=asyncio.Event())
        async with rs._lock:
            rs._waiters.extend([w1, w2])
            # When 0 available, neither can acquire, so both are considered first eligible relative to themselves
            assert rs._is_first_eligible(1) is True
            # When seq not found and no waiter can acquire, fallback returns True
            assert rs._is_first_eligible(999) is True

        await rs.release(t)
        async with rs._lock:
            # Now 2 available, w1 can acquire, so w2 is NOT first eligible
            assert rs._is_first_eligible(1) is False
            assert rs._is_first_eligible(0) is True
            # Clean up test waiters
            rs._waiters.clear()

    async def test_fair_fifo_order_among_eligible_waiters(self):
        rs = AsyncResourceSemaphore(resources={"cpu": 1})
        t = await rs.acquire({"cpu": 1})

        order = []
        done = asyncio.Event()

        async def worker(worker_id):
            async with rs.claim({"cpu": 1}):
                order.append(worker_id)
                await asyncio.wait_for(done.wait(), timeout=5)

        t1 = asyncio.create_task(worker(1))
        await _wait_for_waiters(rs, 1)

        t2 = asyncio.create_task(worker(2))
        await _wait_for_waiters(rs, 2)

        await rs.release(t)
        deadline = asyncio.get_running_loop().time() + 5.0
        while asyncio.get_running_loop().time() < deadline and not order:
            await asyncio.sleep(0.001)

        assert order == [1]
        done.set()
        await asyncio.gather(t1, t2)
        assert order == [1, 2]

    async def test_small_request_bypasses_blocked_large_waiter(self):
        rs = AsyncResourceSemaphore(resources={"cpu": 2})
        t1 = await rs.acquire({"cpu": 1})
        t2 = await rs.acquire({"cpu": 1})

        bypasser_acquired = asyncio.Event()
        bypasser_done = asyncio.Event()

        async def large_worker():
            async with rs.claim({"cpu": 2}):
                pass

        async def small_worker():
            async with rs.claim({"cpu": 1}):
                bypasser_acquired.set()
                await asyncio.wait_for(bypasser_done.wait(), timeout=5)

        t_large = asyncio.create_task(large_worker())
        await _wait_for_waiters(rs, 1)

        # Release only 1 CPU (large worker cannot fit yet)
        await rs.release(t1)

        t_small = asyncio.create_task(small_worker())
        await asyncio.wait_for(bypasser_acquired.wait(), timeout=5)
        async with rs._lock:
            assert len(rs._waiters) == 1
        bypasser_done.set()
        await t_small

        await rs.release(t2)
        await t_large


class TestShutdown:
    async def test_shutdown_wakes_blocked_acquire(self, async_semaphore_cls):
        rs = async_semaphore_cls(resources={"cpu": 1})
        _ticket = await rs.acquire({"cpu": 1})

        errors = []

        async def blocked_acquire():
            try:
                _ticket = await rs.acquire({"cpu": 1})
            except SemaphoreError as e:
                errors.append(e)

        t = asyncio.create_task(blocked_acquire())

        await _wait_for_waiters(rs, 1)
        await rs.shutdown()
        await asyncio.wait_for(t, timeout=5)

        assert len(errors) == 1
        assert "shut down" in str(errors[0])

    async def test_acquire_after_shutdown_raises(self, async_semaphore_cls):
        rs = async_semaphore_cls(resources={"cpu": 1})
        await rs.shutdown()
        with pytest.raises(SemaphoreError, match="shut down"):
            await rs.acquire({"cpu": 1})

    async def test_release_after_shutdown_succeeds(self, async_semaphore_cls):
        rs = async_semaphore_cls(resources={"cpu": 2})
        ticket = await rs.acquire({"cpu": 2})
        await rs.shutdown()
        await rs.release(ticket)
        assert rs.available == {"cpu": 2}

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
            await _wait_for_waiters(rs, 1)
            await rs.release(ticket1)

        task = asyncio.create_task(delayed_release())

        ticket2 = await rs.acquire({"cpu": 1}, timeout=5.0)
        assert rs.available == {"cpu": 0}
        await rs.release(ticket2)
        await task

    async def test_acquire_timeout_raises(self, async_semaphore_cls):
        rs = async_semaphore_cls({"cpu": 1})
        await rs.acquire({"cpu": 1})

        with pytest.raises(TimeoutError, match="Timed out"):
            await rs.acquire({"cpu": 1}, timeout=0.01)

    async def test_claim_timeout_raises(self, async_semaphore_cls):
        rs = async_semaphore_cls({"cpu": 1})
        await rs.acquire({"cpu": 1})

        with pytest.raises(TimeoutError, match="Timed out"):
            async with rs.claim({"cpu": 1}, timeout=0.01):
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
