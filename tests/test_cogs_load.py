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


def test_gamevox_partial_app_info_does_not_crash():
    from omnibot.bot import _complete_app_info

    bot = OmniBot()
    # GameVox-style payload: no owner / verify_key / bot flags
    data = _complete_app_info({"id": "42", "name": "Omni"}, None)
    info = discord.AppInfo(bot._connection, data)
    assert info.id == 42 and info.owner is not None
    # Discord-style full payload is left untouched
    full = {"id": "1", "name": "n", "description": "d", "icon": None, "bot_public": True,
            "bot_require_code_grant": False, "verify_key": "k",
            "owner": {"id": "9", "username": "me", "discriminator": "0", "avatar": None}}
    assert _complete_app_info(full, None) == full


def test_platform_gateway_is_url_object():
    import yarl
    from discord.gateway import DiscordWebSocket

    from omnibot.platform import configure_platform

    try:
        assert configure_platform("gamevox") == "gamevox"
        gw = DiscordWebSocket.DEFAULT_GATEWAY
        assert isinstance(gw, yarl.URL)
        assert str(gw.with_query(v=10, encoding="json")) == "wss://gateway.gamevox.com/?v=10&encoding=json"
    finally:
        configure_platform("discord")
    assert isinstance(DiscordWebSocket.DEFAULT_GATEWAY, yarl.URL)
    assert DiscordWebSocket.DEFAULT_GATEWAY.host == "gateway.discord.gg"


def test_one_by_one_sync_skips_bad_commands():
    async def run():
        bot = OmniBot()
        for name in ("utilities", "fun"):
            await bot.load_extension(f"omnibot.cogs.{name}")
        bot._connection.application_id = 1
        calls = []

        async def upsert(app_id, payload):
            calls.append(payload["name"])
            if payload["name"] == "util" and "contexts" in payload:
                raise discord.HTTPException(type("R", (), {"status": 400, "reason": "Bad"})(), "Invalid Form Body")
            return payload

        bot.http.upsert_global_command = upsert
        assert await bot._sync_one_by_one() is True
        assert calls.count("util") == 2  # retried without optional keys
        await bot.close()

    asyncio.run(run())


def test_gamevox_reserved_names_are_renamed_or_dropped():
    from omnibot.bot import GAMEVOX_RENAMES, GAMEVOX_RESERVED

    async def run():
        bot = OmniBot()
        bot.platform = "gamevox"
        for name in COGS:
            await bot.load_extension(f"omnibot.cogs.{name}")
        bot._adapt_commands_for_gamevox()
        names = {c.name for c in bot.tree.get_commands()}
        assert not names & GAMEVOX_RESERVED
        for new in GAMEVOX_RENAMES.values():
            assert new in names
        for c in bot.tree.get_commands():
            c.to_dict(bot.tree)
        await bot.close()

    asyncio.run(run())


def test_privileged_intents_fallback():
    async def run():
        bot = OmniBot()
        tried = []

        async def fake_login(token):
            return None

        async def fake_connect(reconnect=True):
            i = bot._connection._intents
            tried.append((i.members, i.message_content))
            if i.members:  # pretend Server Members isn't enabled in the portal
                raise discord.PrivilegedIntentsRequired(None)

        bot.login = fake_login
        bot.connect = fake_connect
        await bot.start("x")
        assert tried == [(True, True), (False, True)]
        assert bot._connection._chunk_guilds is False
        await bot.close()

    asyncio.run(run())
