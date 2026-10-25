import asyncio
from pathlib import Path

import discord

from omnibot.bot import OmniBot

COGS = sorted(p.stem for p in (Path(__file__).resolve().parent.parent / "omnibot" / "cogs").glob("*.py")
              if not p.name.startswith("_"))


def test_all_cogs_load_and_commands_serialise():
    async def run():
        bot = OmniBot()
        failed = []
        for name in COGS:
            try:
                await bot.load_extension(f"omnibot.cogs.{name}")
            except Exception as e:  # pragma: no cover - reported below
                failed.append(f"{name}: {e!r}")
        assert not failed, failed
        cmds = bot.tree.get_commands()
        assert len(cmds) <= 100, "Discord allows at most 100 global slash commands"
        for c in cmds:
            c.to_dict(bot.tree)
        assert bot.allowed_mentions.everyone is False
        assert bot.allowed_mentions.roles is False
        for name in list(bot.extensions):
            await bot.unload_extension(name)
        await bot.close()

    asyncio.run(run())


def test_social_normalise():
    from omnibot.services.social_feeds import FeedError, normalise

    assert normalise("youtube", "https://www.youtube.com/@MrBeast") == ("youtube", "@MrBeast")
    assert normalise("youtube", "UCX6OQ3DkcsbYNE6H8uQQuVA") == ("youtube", "UCX6OQ3DkcsbYNE6H8uQQuVA")
    assert normalise("reddit", "r/python") == ("reddit", "python")
    for bad in [("x", "elon"), ("tiktok", "a"), ("reddit", "<script>")]:
        try:
            normalise(*bad)
        except FeedError:
            continue
        raise AssertionError(bad)
    assert discord  # keep import used
