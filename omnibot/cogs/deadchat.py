"""Dead chat reviver — packs from dashboard or /deadchat pack."""
from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from omnibot import storage
from omnibot.services.question_packs import PACK_LABELS, list_packs, pick_question


def _packs_from_cfg(dc: dict) -> list[str]:
    flags = dc.get("packFlags") or {}
    if flags:
        packs = [k for k, v in flags.items() if v]
        return packs or ["general"]
    packs = list(dc.get("packs") or ["general"])
    return packs or ["general"]


class DeadChat(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    deadchat = app_commands.Group(name="deadchat", description="Dead chat reviver settings")

    @deadchat.command(name="setup", description="Enable dead chat and set channel + silence minutes")
    @app_commands.describe(
        channel="Channel to revive",
        minutes="Minutes of silence before a question (min 5)",
        enabled="Turn the reviver on or off",
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def setup(
        self,
        interaction: discord.Interaction,
        channel: discord.TextChannel,
        minutes: app_commands.Range[int, 5, 1440] = 60,
        enabled: bool = True,
    ):
        def mut(d):
            dc = d.setdefault("deadChat", {})
            dc["enabled"] = enabled
            dc["channelId"] = str(channel.id)
            dc["minutes"] = int(minutes)
            dc.setdefault("packFlags", {"general": True})
            dc.pop("message", None)
            dc.pop("customQuestions", None)

        storage.update_guild(interaction.guild.id, mut)  # type: ignore
        await interaction.response.send_message(
            f"Dead chat {'**on**' if enabled else '**off**'} in {channel.mention} "
            f"after **{minutes}** min silence.\n"
            f"Toggle packs in the dashboard (Engagement) or `/deadchat pack`.",
            ephemeral=True,
        )

    @deadchat.command(name="packs", description="List available question packs")
    async def packs(self, interaction: discord.Interaction):
        data = storage.load_guild(interaction.guild.id) if interaction.guild else {}  # type: ignore
        dc = data.get("deadChat") or {}
        active = set(_packs_from_cfg(dc))
        lines = []
        for pid in list_packs():
            mark = "✅" if pid in active else "⬜"
            lines.append(f"{mark} **{pid}** — {PACK_LABELS.get(pid, pid)}")
        await interaction.response.send_message(
            "**Question packs** (toggle in dashboard or `/deadchat pack`)\n" + "\n".join(lines),
            ephemeral=True,
        )

    @deadchat.command(name="pack", description="Enable or disable a question pack")
    @app_commands.describe(action="add or remove", pack="Pack id")
    @app_commands.choices(
        action=[
            app_commands.Choice(name="add", value="add"),
            app_commands.Choice(name="remove", value="remove"),
        ],
        pack=[app_commands.Choice(name=p, value=p) for p in list_packs()],
    )
    @app_commands.checks.has_permissions(administrator=True)
    async def pack(
        self,
        interaction: discord.Interaction,
        action: app_commands.Choice[str],
        pack: app_commands.Choice[str],
    ):
        pid = pack.value

        def mut(d):
            dc = d.setdefault("deadChat", {})
            flags = dict(dc.get("packFlags") or {})
            if not flags and dc.get("packs"):
                for p in dc["packs"]:
                    flags[str(p)] = True
            if action.value == "add":
                flags[pid] = True
            else:
                flags[pid] = False
            if not any(flags.values()):
                flags["general"] = True
            dc["packFlags"] = flags
            dc["packs"] = [k for k, v in flags.items() if v]
            dc.pop("message", None)
            dc.pop("customQuestions", None)

        storage.update_guild(interaction.guild.id, mut)  # type: ignore
        data = storage.load_guild(interaction.guild.id)  # type: ignore
        active = _packs_from_cfg(data.get("deadChat") or {})
        await interaction.response.send_message(
            f"Packs active: {', '.join(active)}",
            ephemeral=True,
        )

    @deadchat.command(name="test", description="Post a sample dead-chat question now")
    @app_commands.checks.has_permissions(administrator=True)
    async def test(self, interaction: discord.Interaction):
        data = storage.load_guild(interaction.guild.id)  # type: ignore
        dc = data.get("deadChat") or {}
        q = pick_question(_packs_from_cfg(dc), None)
        emb = discord.Embed(title="💬 Chat reviver", description=q, color=0x5B6CFF)
        emb.set_footer(text="Dead chat · test")
        await interaction.response.send_message(embed=emb)


async def setup(bot: commands.Bot):
    await bot.add_cog(DeadChat(bot))
