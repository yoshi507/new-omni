"""Dead chat reviver — packs, custom questions, commands."""
from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from omnibot import storage
from omnibot.services.question_packs import PACK_LABELS, list_packs, pick_question


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
    @app_commands.checks.has_permissions(manage_guild=True)
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
            dc.setdefault("packs", ["general"])
            dc.setdefault("customQuestions", [])

        storage.update_guild(interaction.guild.id, mut)  # type: ignore
        await interaction.response.send_message(
            f"Dead chat {'**on**' if enabled else '**off**'} in {channel.mention} "
            f"after **{minutes}** min silence.\n"
            f"Add packs with `/deadchat pack` · custom Qs with `/deadchat question add`",
            ephemeral=True,
        )

    @deadchat.command(name="packs", description="List available question packs")
    async def packs(self, interaction: discord.Interaction):
        data = storage.load_guild(interaction.guild.id) if interaction.guild else {}  # type: ignore
        active = (data.get("deadChat") or {}).get("packs") or ["general"]
        lines = []
        for pid in list_packs():
            mark = "✅" if pid in active else "⬜"
            lines.append(f"{mark} **{pid}** — {PACK_LABELS.get(pid, pid)}")
        await interaction.response.send_message(
            "**Question packs**\n" + "\n".join(lines) + "\n\nToggle with `/deadchat pack add|remove`",
            ephemeral=True,
        )

    @deadchat.command(name="pack", description="Enable or disable a question pack")
    @app_commands.describe(action="add or remove", pack="Pack id (general, fun, gaming, anime, science, facts, music, movies)")
    @app_commands.choices(
        action=[
            app_commands.Choice(name="add", value="add"),
            app_commands.Choice(name="remove", value="remove"),
        ],
        pack=[app_commands.Choice(name=p, value=p) for p in list_packs()],
    )
    @app_commands.checks.has_permissions(manage_guild=True)
    async def pack(
        self,
        interaction: discord.Interaction,
        action: app_commands.Choice[str],
        pack: app_commands.Choice[str],
    ):
        pid = pack.value

        def mut(d):
            dc = d.setdefault("deadChat", {})
            packs = list(dc.get("packs") or ["general"])
            if action.value == "add":
                if pid not in packs:
                    packs.append(pid)
            else:
                packs = [p for p in packs if p != pid]
                if not packs:
                    packs = ["general"]
            dc["packs"] = packs

        storage.update_guild(interaction.guild.id, mut)  # type: ignore
        data = storage.load_guild(interaction.guild.id)  # type: ignore
        active = (data.get("deadChat") or {}).get("packs") or []
        await interaction.response.send_message(
            f"Packs active: {', '.join(active)}",
            ephemeral=True,
        )

    question = app_commands.Group(name="question", parent=deadchat, description="Custom questions")

    @question.command(name="add", description="Add a custom dead-chat question for this server")
    @app_commands.describe(text="The question to ask when chat is quiet")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def question_add(self, interaction: discord.Interaction, text: str):
        text = text.strip()[:300]
        if len(text) < 5:
            return await interaction.response.send_message("Question too short.", ephemeral=True)

        def mut(d):
            dc = d.setdefault("deadChat", {})
            qs = list(dc.get("customQuestions") or [])
            if text not in qs:
                qs.append(text)
            dc["customQuestions"] = qs[:100]

        storage.update_guild(interaction.guild.id, mut)  # type: ignore
        await interaction.response.send_message(f"Added custom question:\n> {text}", ephemeral=True)

    @question.command(name="remove", description="Remove a custom question (exact text or index)")
    @app_commands.describe(text_or_index="Exact question text, or 1-based index from /deadchat question list")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def question_remove(self, interaction: discord.Interaction, text_or_index: str):
        data = storage.load_guild(interaction.guild.id)  # type: ignore
        qs = list((data.get("deadChat") or {}).get("customQuestions") or [])
        removed = None
        if text_or_index.isdigit():
            idx = int(text_or_index) - 1
            if 0 <= idx < len(qs):
                removed = qs.pop(idx)
        else:
            target = text_or_index.strip().lower()
            for i, q in enumerate(qs):
                if q.lower() == target:
                    removed = qs.pop(i)
                    break
        if not removed:
            return await interaction.response.send_message("Not found.", ephemeral=True)

        def mut(d):
            d.setdefault("deadChat", {})["customQuestions"] = qs

        storage.update_guild(interaction.guild.id, mut)  # type: ignore
        await interaction.response.send_message(f"Removed:\n> {removed}", ephemeral=True)

    @question.command(name="list", description="List custom questions for this server")
    async def question_list(self, interaction: discord.Interaction):
        data = storage.load_guild(interaction.guild.id)  # type: ignore
        qs = (data.get("deadChat") or {}).get("customQuestions") or []
        if not qs:
            return await interaction.response.send_message(
                "No custom questions. Add with `/deadchat question add`.",
                ephemeral=True,
            )
        lines = [f"**{i+1}.** {q}" for i, q in enumerate(qs[:40])]
        await interaction.response.send_message("\n".join(lines), ephemeral=True)

    @deadchat.command(name="test", description="Post a sample dead-chat question now")
    @app_commands.checks.has_permissions(manage_guild=True)
    async def test(self, interaction: discord.Interaction):
        data = storage.load_guild(interaction.guild.id)  # type: ignore
        dc = data.get("deadChat") or {}
        q = pick_question(dc.get("packs"), dc.get("customQuestions"))
        emb = discord.Embed(
            title="💬 Chat reviver",
            description=q,
            color=0x5B6CFF,
        )
        emb.set_footer(text="Dead chat · test")
        await interaction.response.send_message(embed=emb)


async def setup(bot: commands.Bot):
    await bot.add_cog(DeadChat(bot))
