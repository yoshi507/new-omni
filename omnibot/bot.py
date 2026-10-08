"""discord.py bot client + cog loader."""
from __future__ import annotations

import logging
import traceback
from pathlib import Path

import discord
from discord.ext import commands

from omnibot.config import settings
from omnibot import storage

log = logging.getLogger("omnibot.bot")

INTENTS = discord.Intents.default()
INTENTS.message_content = True
INTENTS.members = True
INTENTS.guilds = True
INTENTS.moderation = True
INTENTS.reactions = True
INTENTS.invites = True
INTENTS.emojis = True


def _prefix(bot: commands.Bot, message: discord.Message):
    """No text prefixes (!, ?, omni, …). Mention-only fallback for legacy ctx tools."""
    return commands.when_mentioned(bot, message)


class OmniBot(commands.Bot):
    def __init__(self) -> None:
        super().__init__(
            command_prefix=_prefix,
            intents=INTENTS,
            help_command=None,
            case_insensitive=True,
        )
        self.deploy_marker = "2026-10-08-slash-only-no-prefix"

    async def setup_hook(self) -> None:
        cogs_dir = Path(__file__).parent / "cogs"
        for path in sorted(cogs_dir.glob("*.py")):
            if path.name.startswith("_"):
                continue
            ext = f"omnibot.cogs.{path.stem}"
            try:
                await self.load_extension(ext)
                log.info("Loaded cog %s", ext)
            except Exception:
                log.error("Failed to load %s:\n%s", ext, traceback.format_exc())

        try:
            synced = await self.tree.sync()
            log.info("Synced %s application command(s)", len(synced))
        except Exception:
            log.exception("Slash sync failed")

    async def on_ready(self) -> None:
        log.info(
            "✅ OmniBot online as %s · guilds=%s · marker=%s",
            self.user,
            len(self.guilds),
            self.deploy_marker,
        )
        await self.change_presence(
            activity=discord.Activity(
                type=discord.ActivityType.watching,
                name="/help · @mention for AI",
            )
        )

    async def on_command_error(self, ctx: commands.Context, error: Exception) -> None:
        if isinstance(error, commands.CommandNotFound):
            return
        if isinstance(error, commands.MissingPermissions):
            await ctx.reply("You don't have permission to use that command.", mention_author=False)
            return
        if isinstance(error, commands.BotMissingPermissions):
            await ctx.reply("I'm missing permissions to do that.", mention_author=False)
            return
        log.error("Command error in %s: %s", ctx.command, error)
        try:
            await ctx.reply("Something went wrong running that command.", mention_author=False)
        except Exception:
            pass
