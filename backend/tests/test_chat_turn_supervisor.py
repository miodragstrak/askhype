import asyncio
from uuid import uuid4

import pytest

from app.services.chat_turn_supervisor import ChatTurnSupervisor, SupervisorUnavailable


def test_capacity_released_after_success_and_observed_exception(caplog):
    async def run():
        supervisor = ChatTurnSupervisor(1, .1)
        gate = asyncio.Event()

        async def work(_):
            await gate.wait()

        async def fail(_):
            raise RuntimeError("sensitive synthetic text")

        first, _ = supervisor.start(uuid4(), work)
        with pytest.raises(SupervisorUnavailable):
            supervisor.start(uuid4(), work)
        gate.set()
        await first
        failed, _ = supervisor.start(uuid4(), fail)
        await asyncio.wait([failed])  # Only the supervisor reads the exception.
        last, _ = supervisor.start(uuid4(), work)
        await last
        await supervisor.shutdown()

    asyncio.run(run())
    assert "turn_task_failed" in caplog.text
    assert "sensitive synthetic text" not in caplog.text


@pytest.mark.parametrize("finish_before_deadline", [True, False])
def test_shutdown_drains_or_cancels_without_accepting_new_work(finish_before_deadline):
    async def run():
        supervisor = ChatTurnSupervisor(1, .1 if finish_before_deadline else 0)
        gate = asyncio.Event()
        drained = asyncio.Event()

        async def work(_):
            await gate.wait()
            drained.set()

        task, _ = supervisor.start(uuid4(), work)
        shutdown = asyncio.create_task(supervisor.shutdown())
        await asyncio.sleep(0)
        with pytest.raises(SupervisorUnavailable):
            supervisor.start(uuid4(), work)
        if finish_before_deadline:
            gate.set()
        await asyncio.wait_for(shutdown, 2)
        assert task.cancelled() is not finish_before_deadline
        assert drained.is_set() is finish_before_deadline

    asyncio.run(run())


def test_shutdown_deadline_is_bounded_even_if_task_delays_cancellation(caplog):
    async def run():
        supervisor = ChatTurnSupervisor(1, 0)
        entered, release = asyncio.Event(), asyncio.Event()

        async def work(_):
            entered.set()
            try:
                await asyncio.Future()
            except asyncio.CancelledError:
                await release.wait()

        task, _ = supervisor.start(uuid4(), work)
        await entered.wait()
        try:
            await asyncio.wait_for(supervisor.shutdown(), 2)
            assert not task.done()
        finally:
            release.set()
            await task

    asyncio.run(run())
    assert "'remaining': 1" in caplog.text
