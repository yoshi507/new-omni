"""Per-guild concurrency gate — max 4 in-flight work items per server."""
from __future__ import annotations

import asyncio
from collections import defaultdict
from contextlib import asynccontextmanager
from typing import AsyncIterator

# Hard cap: each guild may only process this many concurrent heavy tasks
MAX_PER_GUILD = 4

_semaphores: dict[str, asyncio.Semaphore] = {}
_meta_lock = asyncio.Lock()


async def _sem(guild_id: int | str) -> asyncio.Semaphore:
    key = str(guild_id)
    async with _meta_lock:
        if key not in _semaphores:
            _semaphores[key] = asyncio.Semaphore(MAX_PER_GUILD)
        return _semaphores[key]


@asynccontextmanager
async def guild_slot(guild_id: int | str | None) -> AsyncIterator[None]:
    """
    Acquire one of 4 concurrent slots for this guild.
    If guild_id is None, no limiting is applied.
    """
    if guild_id is None:
        yield
        return
    sem = await _sem(guild_id)
    await sem.acquire()
    try:
        yield
    finally:
        sem.release()


async def try_acquire(guild_id: int | str | None, timeout: float = 0.05) -> bool:
    """Non-blocking-ish check; returns False if all 4 slots are busy."""
    if guild_id is None:
        return True
    sem = await _sem(guild_id)
    try:
        await asyncio.wait_for(sem.acquire(), timeout=timeout)
        return True
    except asyncio.TimeoutError:
        return False


def release(guild_id: int | str | None) -> None:
    if guild_id is None:
        return
    key = str(guild_id)
    sem = _semaphores.get(key)
    if sem is not None:
        try:
            sem.release()
        except ValueError:
            pass


def busy_count(guild_id: int | str) -> int:
    """Approximate in-flight count (MAX - available)."""
    key = str(guild_id)
    sem = _semaphores.get(key)
    if sem is None:
        return 0
    available = getattr(sem, "_value", 4)
    return max(0, 4 - int(available))
