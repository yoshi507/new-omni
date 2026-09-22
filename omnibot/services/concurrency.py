"""
Global resource gate for OmniBot.

- At most GLOBAL_MAX (10) heavy tasks across the entire bot process.
- At most 1 heavy task per guild at a time.
- Extra requests wait in a FIFO queue (asyncio Semaphore), they are not rejected.
"""
from __future__ import annotations

import asyncio
import contextvars
from contextlib import asynccontextmanager
from typing import AsyncIterator

GLOBAL_MAX = 10
PER_GUILD_MAX = 1

_global_sem: asyncio.Semaphore | None = None
_guild_sems: dict[str, asyncio.Semaphore] = {}
_meta_lock = asyncio.Lock()

_held: contextvars.ContextVar[bool] = contextvars.ContextVar("omnibot_conc_held", default=False)


def _ensure_global() -> asyncio.Semaphore:
    global _global_sem
    if _global_sem is None:
        _global_sem = asyncio.Semaphore(GLOBAL_MAX)
    return _global_sem


async def _guild_sem(guild_id: int | str) -> asyncio.Semaphore:
    key = str(guild_id)
    async with _meta_lock:
        if key not in _guild_sems:
            _guild_sems[key] = asyncio.Semaphore(PER_GUILD_MAX)
        return _guild_sems[key]


@asynccontextmanager
async def guild_slot(guild_id: int | str | None) -> AsyncIterator[None]:
    """
    Wait (queue) until:
      1) this guild has a free local slot (max 1), and
      2) a global slot is free (max 10 across all guilds).

    Nested calls in the same task are no-ops (safe for voice→AI).
    """
    if guild_id is None:
        yield
        return

    if _held.get():
        yield
        return

    gsem = await _guild_sem(guild_id)
    glob = _ensure_global()

    await gsem.acquire()
    try:
        await glob.acquire()
        token = _held.set(True)
        try:
            yield
        finally:
            _held.reset(token)
            glob.release()
    finally:
        gsem.release()


async def acquire(guild_id: int | str | None, timeout: float | None = None) -> bool:
    if guild_id is None:
        return True
    if _held.get():
        return True

    gsem = await _guild_sem(guild_id)
    glob = _ensure_global()

    async def _take():
        await gsem.acquire()
        try:
            await glob.acquire()
        except BaseException:
            gsem.release()
            raise

    try:
        if timeout is None:
            await _take()
        else:
            await asyncio.wait_for(_take(), timeout=timeout)
        _held.set(True)
        return True
    except asyncio.TimeoutError:
        return False


def release(guild_id: int | str | None) -> None:
    if guild_id is None:
        return
    try:
        _held.set(False)
    except Exception:
        pass
    key = str(guild_id)
    gsem = _guild_sems.get(key)
    glob = _global_sem
    if glob is not None:
        try:
            glob.release()
        except ValueError:
            pass
    if gsem is not None:
        try:
            gsem.release()
        except ValueError:
            pass


async def try_acquire(guild_id: int | str | None, timeout: float | None = None) -> bool:
    """Wait in the global+guild queue until a slot is free (queues by default)."""
    return await acquire(guild_id, timeout=timeout)


def stats() -> dict:
    glob = _ensure_global()
    g_avail = getattr(glob, "_value", GLOBAL_MAX)
    return {
        "global_max": GLOBAL_MAX,
        "global_busy": max(0, GLOBAL_MAX - int(g_avail)),
        "per_guild_max": PER_GUILD_MAX,
        "guilds_tracked": len(_guild_sems),
    }
