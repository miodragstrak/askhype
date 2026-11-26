"""Per-worker ownership of ordinary chat tasks from admission to settlement."""

import asyncio
import logging
import os
import socket
from collections.abc import Callable, Coroutine
from dataclasses import dataclass, field
from time import monotonic
from typing import Any
from uuid import UUID

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class TurnTrace:
    turn_id: UUID | None
    instance: str
    started: float = field(default_factory=monotonic)

    def event(self, event: str, *, warning: bool = False, **fields: str | int) -> None:
        logger.log(logging.WARNING if warning else logging.INFO, "chat_turn_lifecycle %s", {
            "event": event,
            "turn_id": str(self.turn_id) if self.turn_id else None,
            "instance": self.instance,
            "elapsed_ms": round((monotonic() - self.started) * 1000),
            **fields,
        })


class SupervisorUnavailable(RuntimeError):
    pass


class ChatTurnSupervisor:
    def __init__(self, capacity: int, drain_seconds: float):
        self.capacity = capacity
        self.drain_seconds = drain_seconds
        self.instance = f"{socket.gethostname()}:{os.getpid()}"
        self._closing = False
        self._active: dict[asyncio.Task, TurnTrace] = {}

    def start(self, turn_id: UUID, run: Callable[[TurnTrace], Coroutine[Any, Any, Any]]):
        trace = TurnTrace(turn_id, self.instance)
        if self._closing or len(self._active) >= self.capacity:
            trace.event("admission_rejected", warning=True,
                        reason="shutdown" if self._closing else "capacity")
            raise SupervisorUnavailable()
        task = asyncio.create_task(run(trace), name=f"chat-turn:{turn_id}")
        self._active[task] = trace
        task.add_done_callback(self._observe)
        trace.event("supervisor_admitted", active=len(self._active))
        return task, trace

    def _observe(self, task: asyncio.Task) -> None:
        trace = self._active.pop(task)
        if task.cancelled():
            trace.event("turn_task_cancelled", reason="shutdown" if self._closing else "execution_cancelled")
        elif (error := task.exception()) is not None:
            trace.event("turn_task_failed", warning=True, category=type(error).__name__)

    async def shutdown(self) -> None:
        self._closing = True
        trace = TurnTrace(None, self.instance)
        tasks = set(self._active)
        trace.event("shutdown_started", active=len(tasks))
        pending = set()
        if tasks:
            _, pending = await asyncio.wait(tasks, timeout=self.drain_seconds)
        for task in pending:
            task.cancel()
        if pending:
            _, remaining = await asyncio.wait(pending, timeout=1)
        else:
            remaining = set()
        trace.event("shutdown_finished", warning=bool(remaining), cancelled=len(pending), remaining=len(remaining))
