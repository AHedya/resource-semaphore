from resource_semaphore.base import SemaphoreError, Ticket


def test_ticket_repr():
    ticket = Ticket()
    rep = repr(ticket)
    assert rep.startswith("<Ticket ")
    assert rep.endswith(">")
    assert ticket.id.hex[:8] in rep


def test_semaphore_error():
    err = SemaphoreError("test")
    assert str(err) == "test"
