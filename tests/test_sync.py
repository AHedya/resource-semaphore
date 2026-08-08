import threading
import time
from typing import Literal

import pytest

from resource_semaphore.base import SemaphoreError, Ticket
from resource_semaphore.synchronous import (
    GreedyResourceSemaphore,
    NoopResourceSemaphore,
    ResourceSemaphore,
)


@pytest.fixture(params=[ResourceSemaphore, GreedyResourceSemaphore])
def semaphore_cls(request):
    return request.param


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

        waiting_event = threading.Event()
        acquired = threading.Event()
        done = threading.Event()

        def blocked_claim():
            waiting_event.set()
            with rs.claim({"cpu": 1}):
                acquired.set()
                done.wait(timeout=5)

        t = threading.Thread(target=blocked_claim, daemon=True)
        t.start()

        assert waiting_event.wait(timeout=2)
        time.sleep(0.05)
        assert not acquired.is_set()

        rs.release(ticket)
        assert acquired.wait(timeout=2)
        done.set()
        t.join(timeout=2)


class TestBlockingAcquire:
    def test_acquire_blocks_until_available(self, semaphore_cls):
        rs = semaphore_cls(resources={"cpu": 1})
        ticket = rs.acquire({"cpu": 1})

        waiting_event = threading.Event()
        acquired = threading.Event()
        done = threading.Event()

        def blocked_acquire():
            waiting_event.set()
            _ticket = rs.acquire({"cpu": 1})
            acquired.set()
            done.wait(timeout=5)

        t = threading.Thread(target=blocked_acquire, daemon=True)
        t.start()

        assert waiting_event.wait(timeout=2)
        # Give a tiny bit of time to enter ticket = rs.acquire()'s while loop
        time.sleep(0.05)
        assert not acquired.is_set()

        rs.release(ticket)
        assert acquired.wait(timeout=2)
        done.set()
        t.join(timeout=2)

    def test_atomic_multi_resource_acquire(self, semaphore_cls):
        rs = semaphore_cls(resources={"cpu": 1, "RAM_MB": 1000})
        ticket = rs.acquire({"cpu": 1})

        waiting_event = threading.Event()
        acquired = threading.Event()
        release_event = threading.Event()

        def blocked_acquire():
            waiting_event.set()
            _ticket = rs.acquire({"cpu": 1, "RAM_MB": 500})
            acquired.set()
            release_event.wait(timeout=5)

        t = threading.Thread(target=blocked_acquire, daemon=True)
        t.start()

        assert waiting_event.wait(timeout=2)
        time.sleep(0.05)
        assert not acquired.is_set()

        rs.release(ticket)
        assert acquired.wait(timeout=2)
        assert rs.available == {"cpu": 0, "RAM_MB": 500}
        release_event.set()
        t.join(timeout=2)

    def test_multiple_waiters_woken(self, semaphore_cls):
        rs = semaphore_cls(resources={"cpu": 2})
        ticket = rs.acquire({"cpu": 2})

        waiting_events = [threading.Event() for _ in range(2)]
        events = [threading.Event() for _ in range(2)]
        release_events = [threading.Event() for _ in range(2)]

        def waiter(idx):
            waiting_events[idx].set()
            _ticket = rs.acquire({"cpu": 1})
            events[idx].set()
            release_events[idx].wait(timeout=5)

        threads = [
            threading.Thread(target=waiter, args=(i,), daemon=True) for i in range(2)
        ]
        for t in threads:
            t.start()

        for we in waiting_events:
            assert we.wait(timeout=2)
        time.sleep(0.05)
        assert not any(e.is_set() for e in events)

        rs.release(ticket)

        for e in events:
            assert e.wait(timeout=2)

        for re in release_events:
            re.set()
        for t in threads:
            t.join(timeout=2)


class TestShutdown:
    def test_shutdown_wakes_blocked_acquire(self, semaphore_cls):
        rs = semaphore_cls(resources={"cpu": 1})
        _ticket = rs.acquire({"cpu": 1})

        waiting_event = threading.Event()
        errors = []

        def blocked_acquire():
            waiting_event.set()
            try:
                _ticket = rs.acquire({"cpu": 1})
            except SemaphoreError as e:
                errors.append(e)

        t = threading.Thread(target=blocked_acquire, daemon=True)
        t.start()

        assert waiting_event.wait(timeout=2)
        time.sleep(0.05)
        rs.shutdown()
        t.join(timeout=2)

        assert len(errors) == 1
        assert "shut down" in str(errors[0])

    def test_acquire_after_shutdown_raises(self, semaphore_cls):
        rs = semaphore_cls(resources={"cpu": 1})
        rs.shutdown()
        with pytest.raises(SemaphoreError, match="shut down"):
            rs.acquire({"cpu": 1})

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

        # Release the ticket after 0.1 seconds in a background thread
        threading.Timer(0.1, rs.release, args=(ticket1,)).start()

        # Should succeed because it waits up to 1.0 seconds
        ticket2 = rs.acquire({"cpu": 1}, timeout=1.0)
        assert rs.available == {"cpu": 0}
        rs.release(ticket2)

    def test_acquire_timeout_raises(self, semaphore_cls):
        rs = semaphore_cls({"cpu": 1})
        rs.acquire({"cpu": 1})

        # Should time out because resources are never released
        with pytest.raises(TimeoutError, match="Timed out"):
            rs.acquire({"cpu": 1}, timeout=0.1)

    def test_claim_timeout_raises(self, semaphore_cls):
        rs = semaphore_cls({"cpu": 1})
        rs.acquire({"cpu": 1})

        with pytest.raises(TimeoutError, match="Timed out"):
            with rs.claim({"cpu": 1}, timeout=0.1):
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
