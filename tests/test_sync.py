import threading
import time
from typing import Literal

import pytest

from resource_semaphore.base import SemaphoreError, Ticket
from resource_semaphore.synchronous import (
    GreedyResourceSemaphore,
    NoopResourceSemaphore,
    ResourceSemaphore,
    _SyncWaiter,
)


@pytest.fixture(params=[ResourceSemaphore, GreedyResourceSemaphore])
def semaphore_cls(request):
    return request.param


def _wait_for_waiters(rs, count: int, timeout: float = 5.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        with rs._lock:
            if len(rs._waiters) >= count:
                return
        time.sleep(0.001)
    raise TimeoutError(f"Waiters count did not reach {count} within {timeout}s")


class TestResourceManagerInit:
    def test_basic_creation(self, semaphore_cls):
        rs = semaphore_cls(resources={"cpu": 1, "RAM_MB": 2048})
        assert rs.capacity == {"cpu": 1, "RAM_MB": 2048}
        assert rs.available == {"cpu": 1, "RAM_MB": 2048}

    def test_empty_resources_raises(self, semaphore_cls):
        with pytest.raises(ValueError, match="at least one resource"):
            semaphore_cls(resources={})

    def test_zero_capacity_raises(self, semaphore_cls):
        with pytest.raises(ValueError, match="must be positive"):
            semaphore_cls(resources={"cpu": 0})

    def test_negative_capacity_raises(self, semaphore_cls):
        with pytest.raises(ValueError, match="must be positive"):
            semaphore_cls(resources={"cpu": -1})


class TestAcquireRelease:
    def test_release_invalid_ticket_raises(self, semaphore_cls):
        rs = semaphore_cls(resources={"cpu": 1})
        from resource_semaphore.base import Ticket

        with pytest.raises(ValueError, match="Invalid or already released ticket"):
            rs.release(Ticket())

    def test_acquire_and_release(self, semaphore_cls):
        rs = semaphore_cls(resources={"cpu": 2})
        ticket = rs.acquire({"cpu": 1})
        assert rs.available == {"cpu": 1}
        rs.release(ticket)
        assert rs.available == {"cpu": 2}

    def test_acquire_full_capacity(self, semaphore_cls):
        rs = semaphore_cls(resources={"cpu": 1})
        ticket = rs.acquire({"cpu": 1})
        assert rs.available == {"cpu": 0}
        rs.release(ticket)
        assert rs.available == {"cpu": 1}

    def test_multi_resource_acquire(self, semaphore_cls):
        rs = semaphore_cls(resources={"cpu": 2, "RAM_MB": 2048})
        ticket = rs.acquire({"cpu": 1, "RAM_MB": 500})
        assert rs.available == {"cpu": 1, "RAM_MB": 1548}
        rs.release(ticket)
        assert rs.available == {"cpu": 2, "RAM_MB": 2048}

    def test_acquire_unknown_resource_raises(self, semaphore_cls):
        rs = semaphore_cls(resources={"cpu": 1})
        with pytest.raises(ValueError, match="Unknown resource"):
            rs.acquire({"db_conn": 1})

    def test_acquire_zero_demand_raises(self, semaphore_cls):
        rs = semaphore_cls(resources={"cpu": 1})
        with pytest.raises(ValueError, match="must be positive"):
            rs.acquire({"cpu": 0})

    def test_acquire_negative_demand_raises(self, semaphore_cls):
        rs = semaphore_cls(resources={"cpu": 1})
        with pytest.raises(ValueError, match="must be positive"):
            rs.acquire({"cpu": -1})

    def test_acquire_empty_demands_raises(self, semaphore_cls):
        rs = semaphore_cls(resources={"cpu": 1})
        with pytest.raises(ValueError):
            _ticket = rs.acquire({})

    def test_acquire_exceeding_cap(self, semaphore_cls):
        rs = semaphore_cls(resources={"cpu": 3})
        with pytest.raises(ValueError):
            rs.acquire({"cpu": 5})

    def test_fractional_units_raises(self, semaphore_cls):
        rs = semaphore_cls(resources={"RAM_MB": 2048})
        with pytest.raises(TypeError, match="must be an integer"):
            # type: ignore [bad-assignment]
            rs.acquire({"RAM_MB": 500.1})


class TestClaimContextManager:
    def test_claim_success(self, semaphore_cls):
        rs = semaphore_cls(resources={"cpu": 2})
        with rs.claim({"cpu": 1}):
            assert rs.available == {"cpu": 1}
        assert rs.available == {"cpu": 2}

    def test_claim_exception_releases_resources(self, semaphore_cls):
        rs = semaphore_cls(resources={"cpu": 2})
        try:
            with rs.claim({"cpu": 1}):
                assert rs.available == {"cpu": 1}
                raise RuntimeError("Something went wrong")
        except RuntimeError:
            pass
        assert rs.available == {"cpu": 2}

    def test_claim_blocks_if_unavailable(self, semaphore_cls):
        rs = semaphore_cls(resources={"cpu": 1})
        ticket = rs.acquire({"cpu": 1})

        acquired = threading.Event()
        done = threading.Event()

        def blocked_claim():
            with rs.claim({"cpu": 1}):
                acquired.set()
                done.wait(timeout=5)

        t = threading.Thread(target=blocked_claim, daemon=True)
        t.start()

        _wait_for_waiters(rs, 1)
        assert not acquired.is_set()

        rs.release(ticket)
        assert acquired.wait(timeout=5)
        done.set()
        t.join(timeout=2)


class TestBlockingAcquire:
    def test_acquire_blocks_until_available(self, semaphore_cls):
        rs = semaphore_cls(resources={"cpu": 1})
        ticket = rs.acquire({"cpu": 1})

        acquired = threading.Event()
        done = threading.Event()

        def blocked_acquire():
            _ticket = rs.acquire({"cpu": 1})
            acquired.set()
            done.wait(timeout=5)

        t = threading.Thread(target=blocked_acquire, daemon=True)
        t.start()

        _wait_for_waiters(rs, 1)
        assert not acquired.is_set()

        rs.release(ticket)
        assert acquired.wait(timeout=5)
        done.set()
        t.join(timeout=2)

    def test_atomic_multi_resource_acquire(self, semaphore_cls):
        rs = semaphore_cls(resources={"cpu": 1, "RAM_MB": 1000})
        ticket = rs.acquire({"cpu": 1})

        acquired = threading.Event()
        release_event = threading.Event()

        def blocked_acquire():
            _ticket = rs.acquire({"cpu": 1, "RAM_MB": 500})
            acquired.set()
            release_event.wait(timeout=5)

        t = threading.Thread(target=blocked_acquire, daemon=True)
        t.start()

        _wait_for_waiters(rs, 1)
        assert not acquired.is_set()

        rs.release(ticket)
        assert acquired.wait(timeout=5)
        assert rs.available == {"cpu": 0, "RAM_MB": 500}
        release_event.set()
        t.join(timeout=2)

    def test_multiple_waiters_woken(self, semaphore_cls):
        rs = semaphore_cls(resources={"cpu": 2})
        ticket = rs.acquire({"cpu": 2})

        events = [threading.Event() for _ in range(2)]
        release_events = [threading.Event() for _ in range(2)]

        def waiter(idx):
            _ticket = rs.acquire({"cpu": 1})
            events[idx].set()
            release_events[idx].wait(timeout=5)

        threads = [
            threading.Thread(target=waiter, args=(i,), daemon=True) for i in range(2)
        ]
        for t in threads:
            t.start()

        _wait_for_waiters(rs, 2)
        assert not any(e.is_set() for e in events)

        rs.release(ticket)

        for e in events:
            assert e.wait(timeout=5)

        for re in release_events:
            re.set()
        for t in threads:
            t.join(timeout=2)

    def test_first_eligible_priority(self):

        rs = ResourceSemaphore(resources={"cpu": 2})
        t = rs.acquire({"cpu": 2})

        w1 = _SyncWaiter(seq=0, demands={"cpu": 1}, event=threading.Event())
        w2 = _SyncWaiter(seq=1, demands={"cpu": 1}, event=threading.Event())
        with rs._lock:
            rs._waiters.extend([w1, w2])
            # When 0 available, neither can acquire, so both are considered first eligible relative to themselves
            assert rs._is_first_eligible(1) is True
            # When seq not found and no waiter can acquire, fallback returns True
            assert rs._is_first_eligible(999) is True

        rs.release(t)
        with rs._lock:
            # Now 2 available, w1 can acquire, so w2 is NOT first eligible
            assert rs._is_first_eligible(1) is False
            assert rs._is_first_eligible(0) is True
            # Clean up test waiters
            rs._waiters.clear()

    def test_fair_fifo_order_among_eligible_waiters(self):
        rs = ResourceSemaphore(resources={"cpu": 1})
        t = rs.acquire({"cpu": 1})

        order = []
        done = threading.Event()

        def worker(worker_id):
            with rs.claim({"cpu": 1}):
                order.append(worker_id)
                done.wait(timeout=5)

        t1 = threading.Thread(target=worker, args=(1,), daemon=True)
        t1.start()
        _wait_for_waiters(rs, 1)

        t2 = threading.Thread(target=worker, args=(2,), daemon=True)
        t2.start()
        _wait_for_waiters(rs, 2)

        rs.release(t)
        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline and not order:
            time.sleep(0.001)

        assert order == [1]
        done.set()
        t1.join(timeout=2)
        t2.join(timeout=2)
        assert order == [1, 2]

    def test_small_request_bypasses_blocked_large_waiter(self):
        rs = ResourceSemaphore(resources={"cpu": 2})
        t1 = rs.acquire({"cpu": 1})
        t2 = rs.acquire({"cpu": 1})

        bypasser_acquired = threading.Event()
        bypasser_done = threading.Event()

        def large_worker():
            with rs.claim({"cpu": 2}):
                pass

        def small_worker():
            with rs.claim({"cpu": 1}):
                bypasser_acquired.set()
                bypasser_done.wait(timeout=5)

        # Large worker arrives first when 0 CPUs free
        t_large = threading.Thread(target=large_worker, daemon=True)
        t_large.start()
        _wait_for_waiters(rs, 1)

        # Release only 1 CPU (large worker cannot fit yet)
        rs.release(t1)

        # Small worker arrives later and should bypass large worker
        t_small = threading.Thread(target=small_worker, daemon=True)
        t_small.start()

        assert bypasser_acquired.wait(timeout=5)
        with rs._lock:
            assert len(rs._waiters) == 1
        bypasser_done.set()
        t_small.join(timeout=2)

        # Release remaining CPU so large worker can finally run
        rs.release(t2)
        t_large.join(timeout=2)


class TestShutdown:
    def test_shutdown_wakes_blocked_acquire(self, semaphore_cls):
        rs = semaphore_cls(resources={"cpu": 1})
        _ticket = rs.acquire({"cpu": 1})

        errors = []

        def blocked_acquire():
            try:
                _ticket = rs.acquire({"cpu": 1})
            except SemaphoreError as e:
                errors.append(e)

        t = threading.Thread(target=blocked_acquire, daemon=True)
        t.start()

        _wait_for_waiters(rs, 1)
        rs.shutdown()
        t.join(timeout=5)

        assert len(errors) == 1
        assert "shut down" in str(errors[0])

    def test_acquire_after_shutdown_raises(self, semaphore_cls):
        rs = semaphore_cls(resources={"cpu": 1})
        rs.shutdown()
        with pytest.raises(SemaphoreError, match="shut down"):
            rs.acquire({"cpu": 1})

    def test_release_after_shutdown_succeeds(self, semaphore_cls):
        rs = semaphore_cls(resources={"cpu": 2})
        ticket = rs.acquire({"cpu": 2})
        rs.shutdown()
        # In-flight tickets can still be cleanly released after shutdown
        rs.release(ticket)
        assert rs.available == {"cpu": 2}

    def test_shutdown_idempotent(self, semaphore_cls):
        rs = semaphore_cls(resources={"cpu": 1})
        rs.shutdown()
        rs.shutdown()
        assert rs.is_shutdown


class TestProperties:
    def test_available_snapshot(self, semaphore_cls):
        rs = semaphore_cls(resources={"cpu": 2})
        snap = rs.available
        _ticket = rs.acquire({"cpu": 1})
        assert snap == {"cpu": 2}
        assert rs.available == {"cpu": 1}

    def test_capacity_snapshot(self, semaphore_cls):
        rs = semaphore_cls(resources={"cpu": 2})
        snap = rs.capacity
        assert snap == {"cpu": 2}

    def test_generic_type(self, semaphore_cls):

        _rs = semaphore_cls[Literal["cpu", "RAM_MB"]](resources={"cpu": 2})


class TestTimeout:
    def test_acquire_success_within_timeout(self, semaphore_cls):
        rs = semaphore_cls({"cpu": 1})
        ticket1 = rs.acquire({"cpu": 1})

        def delayed_release():
            _wait_for_waiters(rs, 1)
            rs.release(ticket1)

        t = threading.Thread(target=delayed_release, daemon=True)
        t.start()

        ticket2 = rs.acquire({"cpu": 1}, timeout=5.0)
        assert rs.available == {"cpu": 0}
        rs.release(ticket2)
        t.join(timeout=2.0)

    def test_acquire_timeout_raises(self, semaphore_cls):
        rs = semaphore_cls({"cpu": 1})
        rs.acquire({"cpu": 1})

        with pytest.raises(TimeoutError, match="Timed out"):
            rs.acquire({"cpu": 1}, timeout=0.01)

    def test_claim_timeout_raises(self, semaphore_cls):
        rs = semaphore_cls({"cpu": 1})
        rs.acquire({"cpu": 1})

        with pytest.raises(TimeoutError, match="Timed out"):
            with rs.claim({"cpu": 1}, timeout=0.01):
                pass


def test_noop_semaphore():
    rs = NoopResourceSemaphore()
    assert rs.capacity == {}
    assert rs.available == {}
    assert rs.is_shutdown is False

    ticket = rs.acquire({"cpu": 1})
    assert isinstance(ticket, Ticket)

    rs.release(ticket)

    rs.shutdown()
    assert rs.is_shutdown is False  # type: ignore
