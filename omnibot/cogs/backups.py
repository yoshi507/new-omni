"""Config backup: export as a file, restore from a file, named snapshots."""
from __future__ import annotations

import io
import json
import time

import discord
from discord import app_commands
from discord.ext import commands

from omnibot import storage

# Settings that make up a server's *configuration*. Runtime/user data
# (economy, levels, AI memory, analytics, invites…) is never exported or overwritten.
CONFIG_KEYS = (
    "dashboard", "commandSettings", "persona", "automod", "spamConfig", "smartAutomod",
    "security", "honeypot", "welcomeSettings", "goodbyeSettings", "deadChat",
    "levelSettings", "autorole", "starboard", "stickyRoles", "verification", "booster",
    "boosterRoles", "autoName", "bumpReminder", "social", "suggestions", "birthday",
    "music", "logging", "tickets", "triggers", "customCommands", "tempVoice",
    "serverDocs", "forms", "reactionRoles", "reactionPanels",
)
MAX_SNAPSHOTS = 10
MAX_UPLOAD_BYTES = 512 * 1024


def _config_only(data: dict) -> dict:
    return {k: data[k] for k in CONFIG_KEYS if k in data}


class Backups(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    backup = app_commands.Group(
        name="backup",
        description="Server config backup",
        guild_only=True,
        default_permissions=discord.Permissions(administrator=True),
    )

    @backup.command(name="export", description="Download this server's OmniBot settings as a JSON file")
    @app_commands.checks.has_permissions(administrator=True)
    async def export(self, interaction: discord.Interaction):
        data = storage.load_guild(interaction.guild.id)  # type: ignore[union-attr]
        payload = {
            "omnibotBackup": 1,
            "guildId": str(interaction.guild.id),  # type: ignore[union-attr]
            "exportedAt": int(time.time()),
            "config": _config_only(data),
        }
        buf = io.BytesIO(json.dumps(payload, indent=2, ensure_ascii=False, default=str).encode())
        await interaction.response.send_message(
            "Here's your settings backup. Restore it any time with `/backup restore`.",
            file=discord.File(buf, filename=f"omnibot-backup-{interaction.guild.id}.json"),  # type: ignore[union-attr]
            ephemeral=True,
        )

    @backup.command(name="restore", description="Restore settings from a /backup export file")
    @app_commands.checks.has_permissions(administrator=True)
    async def restore(self, interaction: discord.Interaction, file: discord.Attachment):
        if file.size > MAX_UPLOAD_BYTES:
            return await interaction.response.send_message("That file is too large.", ephemeral=True)
        try:
            payload = json.loads(await file.read())
            config = payload["config"] if isinstance(payload, dict) and "config" in payload else payload
            if not isinstance(config, dict):
                raise ValueError
        except (ValueError, KeyError, UnicodeDecodeError):
            return await interaction.response.send_message(
                "That isn't a valid OmniBot backup file.", ephemeral=True
            )
        applied = [k for k in CONFIG_KEYS if k in config and isinstance(config[k], (dict, list))]
        if not applied:
            return await interaction.response.send_message("No settings found in that file.", ephemeral=True)

        def mut(d):
            for k in applied:
                d[k] = config[k]

        storage.update_guild(interaction.guild.id, mut)  # type: ignore[union-attr]
        await interaction.response.send_message(
            f"Restored {len(applied)} setting group(s). Channel/role IDs from another server won't match.",
            ephemeral=True,
        )

    @backup.command(name="snapshot", description="Save a named settings snapshot")
    @app_commands.checks.has_permissions(administrator=True)
    async def snapshot(self, interaction: discord.Interaction, name: str):
        name = name.strip()[:40]
        data = storage.load_guild(interaction.guild.id)  # type: ignore[union-attr]
        snap = {"savedAt": int(time.time()), "config": _config_only(data)}

        def mut(d):
            snaps = d.setdefault("snapshots", {})
            snaps[name] = snap
            # keep the newest MAX_SNAPSHOTS
            if len(snaps) > MAX_SNAPSHOTS:
                oldest = sorted(snaps, key=lambda k: (snaps[k] or {}).get("savedAt", 0))
                for k in oldest[: len(snaps) - MAX_SNAPSHOTS]:
                    snaps.pop(k, None)

        storage.update_guild(interaction.guild.id, mut)  # type: ignore[union-attr]
        await interaction.response.send_message(f"Snapshot `{name}` saved.", ephemeral=True)

    @backup.command(name="load", description="Restore a named snapshot")
    @app_commands.checks.has_permissions(administrator=True)
    async def load(self, interaction: discord.Interaction, name: str):
        data = storage.load_guild(interaction.guild.id)  # type: ignore[union-attr]
        snap = (data.get("snapshots") or {}).get(name.strip()[:40])
        if not snap:
            return await interaction.response.send_message("No snapshot with that name.", ephemeral=True)
        config = snap.get("config") if isinstance(snap.get("config"), dict) else snap  # old format

        def mut(d):
            for k in CONFIG_KEYS:
                if k in config and config[k] is not None:
                    d[k] = config[k]

        storage.update_guild(interaction.guild.id, mut)  # type: ignore[union-attr]
        await interaction.response.send_message(f"Snapshot `{name}` restored.", ephemeral=True)

    @load.autocomplete("name")
    async def _snap_names(self, interaction: discord.Interaction, current: str):
        data = storage.load_guild(interaction.guild.id)  # type: ignore[union-attr]
        names = list((data.get("snapshots") or {}).keys())
        return [app_commands.Choice(name=n, value=n) for n in names if current.lower() in n.lower()][:25]


async def setup(bot: commands.Bot):
    await bot.add_cog(Backups(bot))
