"""discord.py bot client + cog loader."""
from __future__ import annotations

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
    """No text prefixes (!, ?, omni, …). Mention-only fallback for legacy ctx tools."""
    return commands.when_mentioned(bot, message)


def _complete_app_info(data: dict | None, user: discord.ClientUser | None) -> dict:
    """Fill fields some Discord-compatible platforms (GameVox) leave out of
    /oauth2/applications/@me, so discord.py's AppInfo doesn't KeyError on login."""
    data = dict(data or {})
    uid = str(user.id) if user else str(data.get("id") or "0")
    uname = user.name if user else "OmniBot"
    data.setdefault("id", uid)
    data.setdefault("name", uname)
    data.setdefault("description", "")
    data.setdefault("icon", None)
    data.setdefault("bot_public", False)
    data.setdefault("bot_require_code_grant", False)
    data.setdefault("verify_key", "")
    owner = data.get("owner")
    if not isinstance(owner, dict) or "id" not in owner:
        data["owner"] = {
            "id": uid,
            "username": uname,
            "discriminator": "0",
            "avatar": user.avatar.key if user and user.avatar else None,
            "global_name": None,
        }
    else:
        owner.setdefault("username", "owner")
        owner.setdefault("discriminator", "0")
        owner.setdefault("avatar", None)
    return data


class OmniBot(commands.Bot):
    def __init__(self) -> None:
        super().__init__(
            command_prefix=_prefix,
            intents=INTENTS,
            help_command=None,
            case_insensitive=True,
            # Never let bot output (AI replies, custom commands, panels) ping
            # @everyone/@here or whole roles. Users can still be mentioned.
            allowed_mentions=discord.AllowedMentions(
                everyone=False, roles=False, users=True, replied_user=False
            ),
        )
        self.deploy_marker = DEPLOY_MARKER
        self.platform = getattr(settings, "platform", "discord")

    async def application_info(self) -> discord.AppInfo:
        """Tolerant version: works on Discord and on GameVox's partial payload."""
        try:
            data = await self.http.application_info()
        except discord.HTTPException as e:
            if self.platform == "discord":
                raise
            log.warning("application_info failed on %s (%s) — using bot user as app info", self.platform, e)
            data = {}
        missing = [k for k in ("owner", "verify_key", "bot_public", "description") if k not in (data or {})]
        if missing:
            log.info("App info missing %s on %s — filled defaults", ", ".join(missing), self.platform)
        return discord.AppInfo(self._connection, _complete_app_info(data, self.user))

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
        await self._sync_commands_if_changed()

    async def _sync_commands_if_changed(self) -> None:
        """Global sync only when the command tree changed (saves rate limit + startup time)."""
        marker = DATA_DIR / f"command_tree_{self.platform}.sha256"
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
        try:
            synced = await self.tree.sync()
            log.info("Synced %s application command(s)", len(synced))
            if digest:
                try:
                    marker.write_text(digest)
                except OSError:
                    log.warning("Could not write %s", marker)
        except Exception:
            log.exception("Slash sync failed")

    async def on_app_command_error(
        self, interaction: discord.Interaction, error: app_commands.AppCommandError
    ) -> None:
        """Friendly replies for slash command failures instead of 'did not respond'."""
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
        plat = getattr(self, "platform", "discord")
        log.info(
            "✅ OmniBot online as %s · platform=%s · guilds=%s · marker=%s",
            self.user,
            plat,
            len(self.guilds),
            self.deploy_marker,
        )
        watching = (
            "/help · GameVox"
            if plat == "gamevox"
            else "/help · @mention for AI"
        )
        await self.change_presence(
            activity=discord.Activity(
                type=discord.ActivityType.watching,
                name=watching,
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
