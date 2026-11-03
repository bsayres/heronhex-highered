"""Run several fetches at once under one deadline.

A tool call has to answer inside the client's time limit (about a minute). Work that has not finished by the deadline is not
cancelled: it keeps running and writes its result to the cache, so asking again shortly gets it. Calls for the same job share one
download instead of starting another.
"""
import asyncio
from collections.abc import Awaitable, Callable

DEADLINE = 45.0  # seconds; below the typical client limit of 60

_running: dict[str, asyncio.Task] = {}


def _quiet(task: asyncio.Task) -> None:
    if not task.cancelled():
        task.exception()  # mark as retrieved so a late failure does not log "never retrieved"


def start(name: str, make: Callable[[], Awaitable]) -> asyncio.Task:
    task = _running.get(name)
    if task is None or task.done():
        task = asyncio.ensure_future(make())
        task.add_done_callback(_quiet)
        task.add_done_callback(lambda t, n=name: _running.pop(n, None) if _running.get(n) is t else None)
        _running[name] = task
    return task


async def run(jobs: dict, seconds: float | None = None) -> tuple[dict, dict, list]:
    """jobs maps a key to (job name, zero-argument coroutine function). Returns (results, errors, late keys), each by key."""
    tasks = {k: start(name, make) for k, (name, make) in jobs.items()}
    if not tasks:
        return {}, {}, []
    _done, pending = await asyncio.wait(set(tasks.values()), timeout=DEADLINE if seconds is None else seconds)
    results, errors, late = {}, {}, []
    for k, t in tasks.items():
        if t in pending:
            late.append(k)
        elif t.cancelled():
            errors[k] = asyncio.CancelledError()
        elif t.exception() is not None:
            errors[k] = t.exception()
        else:
            results[k] = t.result()
    return results, errors, late
