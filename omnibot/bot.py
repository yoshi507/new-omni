"""discord.py bot client + cog loader."""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import traceback
from pathlib import Path

import discord
from discord import app_commands
from discord.ext import commands

from omnibot import DEPLOY_MARKER
from omnibot.config import DATA_DIR, settings

_log = logging.getLogger(__name__)
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
    """No text prefixes. Mention-only fallback for legacy ctx tools."""
    return commands.when_mentioned(bot, message)


class OmniBot(commands.Bot):
    def __init__(self) -> None:
        super().__init__(
            command_prefix=_prefix,
            intents=INTENTS,
            help_command=None,
            case_insensitive=True,
            allowed_mentions=discord.AllowedMentions(
                everyone=False, roles=False, users=True, replied_user=False
            ),
        )
        self.deploy_marker = DEPLOY_MARKER

    def _intent_fallbacks(self) -> list[tuple[discord.Intents, str]]:
        full = discord.Intents(**dict(INTENTS))
        no_members = discord.Intents(**dict(INTENTS))
        no_members.members = False
        no_content = discord.Intents(**dict(INTENTS))
        no_content.message_content = False
        neither = discord.Intents(**dict(INTENTS))
        neither.members = neither.message_content = False
        return [
            (full, ""),
            (no_members, "Server Members intent OFF — welcome/goodbye, autorole, member logs won't fire"),
            (no_content, "Message Content intent OFF — automod/triggers can't read messages"),
            (neither, "Server Members + Message Content intents OFF"),
        ]

    def _apply_intents(self, intents: discord.Intents) -> None:
        state = self._connection
        state._intents = intents
        state.member_cache_flags = discord.MemberCacheFlags.from_intents(intents)
        state._chunk_guilds = intents.members

    async def start(self, token: str, *, reconnect: bool = True) -> None:
        await self.login(token)
        portal = "https://discord.com/developers/applications → your app → Bot"
        last_exc: Exception | None = None
        for intents, warning in self._intent_fallbacks():
            self._apply_intents(intents)
            if warning:
                log.warning("Retrying gateway with reduced intents: %s", warning)
            try:
                await self.connect(reconnect=reconnect)
                return
            except discord.PrivilegedIntentsRequired as e:
                last_exc = e
                log.error(
                    "Gateway refused privileged intents (4014). Turn ON "
                    "'Server Members Intent' and 'Message Content Intent' at %s and Save.",
                    portal,
                )
        assert last_exc is not None
        raise last_exc

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

        self.tree.on_error = self.on_app_command_error  # type: ignore[assignment]
        self._sync_task = asyncio.create_task(self._sync_after_ready())

    async def _sync_after_ready(self) -> None:
        try:
            await self.wait_until_ready()
            await self._sync_commands_if_changed()
        except Exception:
            log.exception("Slash command sync crashed")

    async def _sync_commands_if_changed(self) -> None:
        marker = DATA_DIR / "command_tree_discord.sha256"
        try:
            payload = [c.to_dict(self.tree) for c in self.tree.get_commands()]
            digest = hashlib.sha256(
                json.dumps(payload, sort_keys=True, default=str).encode()
            ).hexdigest()
        except Exception:
            log.warning("Could not hash command tree; syncing anyway", exc_info=True)
            digest = ""
        if digest and settings.force_command_sync is False:
            try:
                if marker.read_text().strip() == digest:
                    log.info("Slash commands unchanged — skipping sync")
                    return
            except OSError:
                pass
        ok = False
        try:
            synced = await self.tree.sync()
            log.info("Synced %s application command(s)", len(synced))
            ok = True
        except discord.HTTPException as e:
            log.error(
                "Bulk slash sync failed (HTTP %s, code %s): %s",
                e.status,
                e.code,
                (e.text or "")[:500] or "no details from server",
            )
            ok = await self._sync_one_by_one()
        except Exception:
            log.exception("Slash sync failed")
        if ok and digest:
            try:
                marker.write_text(digest)
            except OSError:
                log.warning("Could not write %s", marker)

    async def _sync_one_by_one(self) -> bool:
        app_id = self.application_id
        if not app_id:
            return False
        cmds = self.tree.get_commands()
        log.info("Uploading %s slash command(s) one at a time…", len(cmds))
        good, skipped = 0, []
        for i, cmd in enumerate(cmds, 1):
            payload = cmd.to_dict(self.tree)
            name = payload.get("name")
            try:
                await self.http.upsert_global_command(app_id, payload)
                good += 1
            except discord.HTTPException as e:
                skipped.append(name)
                log.warning("REJECTED /%s → HTTP %s code %s", name, e.status, e.code)
            if i % 10 == 0:
                log.info("…%s/%s commands processed", i, len(cmds))
            await asyncio.sleep(0.3)
        log.info("Slash upload done: %s ok, %s rejected", good, len(skipped))
        return good > 0

    async def on_app_command_error(
        self, interaction: discord.Interaction, error: app_commands.AppCommandError
    ) -> None:
        if isinstance(error, app_commands.MissingPermissions):
            perms = ", ".join(p.replace("_", " ") for p in error.missing_permissions)
            msg = f"You need **{perms}** to use this command."
        elif isinstance(error, app_commands.BotMissingPermissions):
            perms = ", ".join(p.replace("_", " ") for p in error.missing_permissions)
            msg = f"I'm missing **{perms}** in this channel."
        elif isinstance(error, app_commands.CommandOnCooldown):
            msg = f"Slow down — try again in {error.retry_after:.0f}s."
        elif isinstance(error, app_commands.NoPrivateMessage):
            msg = "This command only works in a server."
        elif isinstance(error, app_commands.CheckFailure):
            msg = "You can't use this command here."
        else:
            cmd = interaction.command.qualified_name if interaction.command else "?"
            log.error(
                "Slash command /%s failed", cmd, exc_info=getattr(error, "original", error)
            )
            msg = "Something went wrong running that command."
        try:
            if interaction.response.is_done():
                await interaction.followup.send(msg, ephemeral=True)
            else:
                await interaction.response.send_message(msg, ephemeral=True)
        except discord.HTTPException:
            pass

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
            _log.debug("Ignored error", exc_info=True)
